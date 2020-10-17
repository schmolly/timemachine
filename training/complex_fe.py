import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt

from jax.config import config as jax_config
jax_config.update("jax_enable_x64", True)

import argparse
import time
import datetime
import numpy as np
import os
import sys
import copy

from fe import standard_state

from ff import handlers
from ff.handlers.serialize import serialize_handlers
from ff.handlers.deserialize import deserialize_handlers

from rdkit import Chem

import configparser
import grpc

from training import dataset
from training import model, setup_system
from training import simulation
from training import service_pb2_grpc

from timemachine.potentials import jax_utils
from timemachine.lib import LangevinIntegrator, potentials
from training import build_system

from simtk import unit
from simtk.openmm import app

# from fe import PDBWriter

# used during visualization to bring everything back to home box
def recenter(conf, box):

    new_coords = []

    periodicBoxSize = box

    for atom in conf:
        diff = np.array([0., 0., 0.])
        diff += periodicBoxSize[2]*np.floor(atom[2]/periodicBoxSize[2][2]);
        diff += periodicBoxSize[1]*np.floor((atom[1]-diff[1])/periodicBoxSize[1][1]);
        diff += periodicBoxSize[0]*np.floor((atom[0]-diff[0])/periodicBoxSize[0][0]);
        new_coords.append(atom - diff)

    return np.array(new_coords)

def add_restraints(combined_coords, ligand_idxs, pocket_idxs, temperature):

    restr_k = 50.0 # force constant for the restraint
    restr_avg_xi = np.mean(combined_coords[ligand_idxs], axis=0)
    restr_avg_xj = np.mean(combined_coords[pocket_idxs], axis=0)
    restr_ctr_dij = np.sqrt(np.sum((restr_avg_xi - restr_avg_xj)**2))

    restr = potentials.CentroidRestraint(
        np.array(ligand_idxs, dtype=np.int32),
        np.array(pocket_idxs, dtype=np.int32),
        masses,
        restr_k,
        restr_ctr_dij,
        precision=np.float32
    )


    ssc = standard_state.harmonic_com_ssc(
        restr_k,
        restr_ctr_dij,
        temperature
    )

    return restr, ssc

    # .bind(np.array([], dtype=np.float64))

def flatten_grads(stage_grads, stage_vjp_fns):

    assert len(stage_grads) == len(stage_vjp_fns)

    handle_and_grads = {}

    for stage, (grads, vjp_fns) in enumerate(zip(stage_grads, stage_vjp_fns)):
        for grad, handle_and_vjp_fns in zip(grads, vjp_fns):
            
            dp = vjp_fn(grad)
            if handle not in handle_and_grads:
                handle_and_grads[handle] = dp
            else:
                handle_and_grads[handle] += dp

    return handle_and_grads

            # handle_and_grads


# (ytz): need to add box to this
def find_protein_pocket_atoms(conf, nha, nwa, search_radius):
    """
    Find atoms in the protein that are close to the binding pocket. This simply grabs the
    protein atoms that are within search_radius nm of each ligand atom.

    The ordering of the atoms in the conformation should be:

    |nha|nwa|nla|

    Where, nha is the number of protein atoms, nwa is the number of water atoms, and nla
    is the number of ligand atoms.

    Parameters
    ----------
    conf: np.array [N,3]
        system coordinates

    nha: int
        number of host atoms

    nwa: int
        number of water atoms

    search_radius: float
        how far we search into the binding pocket.

    """
    # (ytz): this is horribly slow and can be made much faster

    ri = np.expand_dims(conf, axis=0)
    rj = np.expand_dims(conf, axis=1)
    dij = jax_utils.distance(ri, rj)


    # pdd = dij[:(nha+nwa), :(nha+nwa)]
    # pdd = pdd + (np.eye(nha+nwa)*10000)
    # print("SHORTEST DISTANCE", np.amin(pdd))



    pocket_atoms = set()

    for l_idx, dists in enumerate(dij[nha+nwa:]):
        nns = np.argsort(dists[:nha])
        for p_idx in nns:
            if dists[p_idx] < search_radius:
                pocket_atoms.add(p_idx)

    return list(pocket_atoms)

# def setup_restraints(
    # ligand_idxs,
    # pocket_idxs,
    # combined):


if __name__ == "__main__":

    parser = argparse.ArgumentParser(description='Absolute Hydration Free Energy Script')
    parser.add_argument('--config_file', type=str, required=True, help='Location of config file.')
    
    args = parser.parse_args()
    config = configparser.ConfigParser()
    config.read(args.config_file)
    print("Config Settings:")
    config.write(sys.stdout)

    general_cfg = config['general']


    # basic gist of workflow:
    # 1. configure learning rates for the optimizer
    # 2. load freesolv dataset from SDF file
    # 3. split dataset into train/test
    # 4. connect to workers
    # 5. deserialize off smirnoff parameters
    # 6. prepare water box
    # 7. for each epoch, first run on test set then shuffled training set
    # 8. save parameters after each molecule

    # set up learning rates
    learning_rates = {}
    for k, v in config['learning_rates'].items():
        vals = [float(x) for x in v.split(',')]
        if k == 'am1ccc':
            learning_rates[handlers.AM1CCCHandler] = np.array(vals)
        elif k == 'lj':
            learning_rates[handlers.LennardJonesHandler] = np.array(vals)

    intg_cfg = config['integrator']

    suppl = Chem.SDMolSupplier(general_cfg['ligand_sdf'], removeHs=False)

    data = []

    for guest_idx, mol in enumerate(suppl):
        # label_dG = -4.184*float(mol.GetProp(general_cfg['dG'])) # in kcal/mol
        # label_err = 4.184*float(mol.GetProp(general_cfg['dG_err'])) # errs are positive!
        label_dG = 80
        label_err = 0
        data.append((mol, label_dG, label_err))

    full_dataset = dataset.Dataset(data)
    train_frac = float(general_cfg['train_frac'])
    train_dataset, test_dataset = full_dataset.split(train_frac)

    forcefield = general_cfg['forcefield']

    stubs = []

    ff_raw = open(forcefield, "r").read()
    ff_handlers = deserialize_handlers(ff_raw)

    protein_system, protein_coords, nwa, nha, protein_box = build_system.build_protein_system(general_cfg['protein_pdb'])
    water_system, water_coords, water_box = build_system.build_water_system(box_width=3.0)

    # assert 0
    # host_pdbfile = general_cfg['protein_pdb']
    # host_ff = app.ForceField('amber99sbildn.xml', 'tip3p.xml')
    # host_pdb = app.PDBFile(host_pdbfile)

    # modeller = app.Modeller(host_pdb.topology, host_pdb.positions)
    # host_coords = strip_units(host_pdb.positions)

    # padding = 1.0
    # box_lengths = np.amax(host_coords, axis=0) - np.amin(host_coords, axis=0)
    # box_lengths = box_lengths.value_in_unit_system(unit.md_unit_system)
    # box_lengths = box_lengths+padding
    # box = np.eye(3, dtype=np.float64)*box_lengths

    # modeller.addSolvent(host_ff, boxSize=np.diag(box)*unit.nanometers, neutralize=False)
    # solvated_host_coords = strip_units(modeller.positions)

    # PDBFile(modeller.topology, "debug_solvated.pdb")
    # with open("debug_solvated.pdb", "w") as out_file:
        # app.PDBFile.writeHeader(modeller.topology, out_file)
        # app.PDBFile.writeModel(modeller.topology, solvated_host_coords, out_file, 0)
        # app.PDBFile.writeFooter(modeller.topology, out_file)



    # assert 0

    # nha = host_coords.shape[0]
    # nwa = solvated_host_coords.shape[0] - nha

    # print(nha, "protein atoms", nwa, "water atoms")
    # solvated_host_system = host_ff.createSystem(
    #     modeller.topology,
    #     nonbondedMethod=app.NoCutoff,
    #     constraints=None,
    #     rigidWater=False
    # )

    # solvated_water_system = water_b

    # assert 0
    # simulation = Simulation(modeller.topology, system, integrator)
    # simulation.context.setPositions(modeller.positions)
    # box_width = 3.0
    # host_system, host_coords, box, _ = water_box.prep_system(box_width)

    # lambda_schedule = np.array([float(x) for x in general_cfg['lambda_schedule'].split(',')])

    num_steps = int(general_cfg['n_steps'])

    raw_schedules = config['lambda_schedule']
    schedules = {}
    for k, v in raw_schedules.items():
        print(k, v)
        schedules[k] = np.array([float(x) for x in v.split(',')])

    # assert 0

    # move this to model class
    worker_address_list = []
    for address in config['workers']['hosts'].split(','):
        worker_address_list.append(address)

    for address in worker_address_list:
        # print("connecting to", address)
        channel = grpc.insecure_channel(address,
            options = [
                ('grpc.max_send_message_length', 500 * 1024 * 1024),
                ('grpc.max_receive_message_length', 500 * 1024 * 1024)
            ]
        )

        stub = service_pb2_grpc.WorkerStub(channel)
        stubs.append(stub)

    for epoch in range(100):

        print("Starting Epoch", epoch, datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S"))

        epoch_dir = os.path.join(general_cfg["out_dir"], "epoch_"+str(epoch))

        if not os.path.exists(epoch_dir):
            os.makedirs(epoch_dir)

        epoch_params = serialize_handlers(ff_handlers)
        with open(os.path.join(epoch_dir, "start_epoch_params.py"), 'w') as fh:
            fh.write(epoch_params)

        all_data = []

        # fix m
        test_items = [(x, False) for x in test_dataset.data]
        # (ytz): re-enable me
        train_dataset.shuffle()
        train_items = [(x, False) for x in train_dataset.data]

        all_data.extend(test_items)
        all_data.extend(train_items)

        # debug
        all_data = all_data[:1]

        for idx, ((mol, label_dG, label_err), inference) in enumerate(all_data):

            # combined_pdb = Chem.CombineMols(
                # Chem.MolFromPDBFile("debug_solvated.pdb", removeHs=False),
                # mol
            # )
            # combined_pdb_str = Chem.MolToPDBBlock(combined_pdb)
            # with open("holy_debug.pdb", "w") as fh:
                # fh.write(combined_pdb_str

            if inference:
                prefix = "test"
            else:
                prefix = "train"

            ligand_idxs = np.arange(mol.GetNumAtoms()) + nha + nwa

            start_time = time.time()

            # restraints
            # combined_potentials.append(restraint)
            # vjp_fns.append([])

            # seed = np.random.randint(0, np.iinfo(np.int32).max)
            seed = 0 # zero seed will let worker randomize it.

            stage_dGs = []
            # stage_vjp_fns = []
            # stage_grads = []

            handle_and_grads = {}

            for stage in [0,1,2]:

                if stage == 0:
                    # out_dir = os.path.join(epoch_dir, "mol_"+mol.GetProp("_Name"))\
                    # if not os.path.exists(out_dir):
                        # os.makedirs(out_dir)

                    # safety guard
                    # try:

                    guest_lambda_offset_idxs = np.ones(mol.GetNumAtoms(), dtype=np.int32) 

                    combined_potentials, masses, vjp_fns = setup_system.combine_potentials(
                        ff_handlers,
                        mol,
                        water_system,
                        guest_lambda_offset_idxs,
                        precision=np.float32
                    )

                    combined_coords = setup_system.combine_coordinates(
                        water_coords,
                        mol
                    )

                    lambda_schedule = schedules['solvent']

                    simulation_box = water_box

                if stage == 1:

                    guest_lambda_offset_idxs = np.zeros(mol.GetNumAtoms(), dtype=np.int32) 

                    combined_potentials, masses, vjp_fns = setup_system.combine_potentials(
                        ff_handlers,
                        mol,
                        protein_system,
                        guest_lambda_offset_idxs,
                        precision=np.float32
                    )

                    combined_coords = setup_system.combine_coordinates(
                        protein_coords,
                        mol
                    )

                    pocket_idxs = find_protein_pocket_atoms(combined_coords, nha, nwa, 0.4)

                    restraint_potential, ssc = add_restraints(
                        combined_coords,
                        ligand_idxs,
                        pocket_idxs,
                        float(intg_cfg['temperature'])
                    )
                    restr = potentials.LambdaPotential(restraint_potential, len(masses), 0).bind(np.array([]))
                    combined_potentials.append(restr)
                    vjp_fns.append([])

                    lambda_schedule = schedules['complex_restraints']
                    simulation_box = protein_box

                if stage == 2:

                    guest_lambda_offset_idxs = np.ones(mol.GetNumAtoms(), dtype=np.int32) 

                    combined_potentials, masses, vjp_fns = setup_system.combine_potentials(
                        ff_handlers,
                        mol,
                        protein_system,
                        guest_lambda_offset_idxs,
                        precision=np.float32
                    )

                    combined_coords = setup_system.combine_coordinates(
                        protein_coords,
                        mol
                    )

                    pocket_idxs = find_protein_pocket_atoms(combined_coords, nha, nwa, 0.4)

                    restraint_potential, ssc = add_restraints(
                        combined_coords,
                        ligand_idxs,
                        pocket_idxs,
                        float(intg_cfg['temperature'])
                    )
                    combined_potentials.append(restraint_potential.bind(np.array([])))
                    vjp_fns.append([])

                    lambda_schedule = schedules['complex_decouple']
                    simulation_box = protein_box

                intg = LangevinIntegrator(
                    float(intg_cfg['temperature']),
                    float(intg_cfg['dt']),
                    float(intg_cfg['friction']),
                    masses,
                    seed
                )

                # tbd fix me and check boundary errors
                simulation_box = simulation_box + np.eye(3)+0.2

                sim = simulation.Simulation(
                    combined_coords,
                    np.zeros_like(combined_coords),
                    simulation_box,
                    combined_potentials,
                    intg
                )

                # (pred_dG, pred_err), grad_dG, du_dls = model.simulate(
                du_dls, grad_dG = model.simulate(
                    sim,
                    num_steps,
                    lambda_schedule,
                    stubs
                )

                dG = np.trapz(du_dls, lambda_schedule)
                stage_dGs.append(dG)

                for grad, handle_and_vjp_fns in zip(grad_dG, vjp_fns):
                    for handle, vjp_fn in handle_and_vjp_fns:
                        dp = vjp_fn(grad)[0]
                        if handle not in handle_and_grads:
                            handle_and_grads[handle] = dp
                        else:
                            handle_and_grads[handle] += dp

                # stage_grads.append(grad_dG)
                # stage_vjp_fns.append(vjp_fns)

                print(stage, dG)

                plt.plot(lambda_schedule, du_dls)
                plt.ylabel("du_dlambda")
                plt.xlabel("lambda")
                plt.savefig(os.path.join(epoch_dir, "ti_mol_"+mol.GetProp("_Name")))
                plt.clf()

            print(stage_dGs, ssc)
            pred_dG = np.sum(stage_dGs) - ssc

            loss = np.abs(pred_dG - label_dG)

            # (ytz) bootstrap CI on TI is super janky
            # error CIs are wrong "95% CI [{:.2f}, {:.2f}, {:.2f}]".format(pred_err.lower_bound, pred_err.value, pred_err.upper_bound),
            print(prefix, "mol", mol.GetProp("_Name"), "loss {:.2f}".format(loss), "pred_dG {:.2f}".format(pred_dG), "label_dG {:.2f}".format(label_dG), "label err {:.2f}".format(label_err), "time {:.2f}".format(time.time() - start_time), "smiles:", Chem.MolToSmiles(mol))

            # update ff parameters
            if not inference:

                loss_grad = np.sign(pred_dG - label_dG)
                # assert len(grad_dG) == len(vjp_fns)

                for handle, grad in handle_and_grads.items():
                    if type(handle) in learning_rates:
                        bounds = learning_rates[type(handle)]

                        dL_dp = loss_grad * grad
                        dL_dp = np.clip(dL_dp, -bounds, bounds)

                        handle.params -= dL_dp

                # for grad, handle_and_vjp_fns in zip(grad_dG, vjp_fns):
                #     for handle, vjp_fn in handle_and_vjp_fns:
                #         if type(handle) in learning_rates:

                #             bounds = learning_rates[type(handle)]
                #             dL_dp = loss_grad*vjp_fn(grad)[0]
                #             dL_dp = np.clip(dL_dp, -bounds, bounds)

                #             handle.params -= dL_dp

                epoch_params = serialize_handlers(ff_handlers)

                # write parameters after each traning molecule
                with open(os.path.join(epoch_dir, "checkpoint_params_idx_"+str(idx)+"_mol_"+mol.GetProp("_Name")+".py"), 'w') as fh:
                    fh.write(epoch_params)

            # assert 0
            # except Exception as e:
            #     import traceback
            #     print("Exception in mol", mol.GetProp("_Name"), Chem.MolToSmiles(mol), e)
            #     traceback.print_exc()


        # epoch_params = serialize_handlers(ff_handlers)
        # with open(os.path.join(epoch_dir, "end_epoch_params.py"), 'w') as fh:
        #     fh.write(epoch_params)