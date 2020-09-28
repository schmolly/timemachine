import functools
import unittest
import scipy.linalg

import numpy as np
import jax
import jax.numpy as jnp
from jax.config import config; config.update("jax_enable_x64", True)
import functools

from common import GradientTest
from timemachine.lib import potentials
from timemachine.potentials import bonded


class TestBonded(GradientTest):

    # def test_centroid_restraint(self):

    #     N = 10

    #     for precision, rtol in [(np.float32, 2e-5), (np.float64, 1e-9)]:

    #         x_primal = self.get_random_coords(N, 3)
    #         x_tangent = np.random.randn(*x_primal.shape)
    #         lamb_tangent = np.random.rand()

    #         gai = np.random.randint(0, N, 4, dtype=np.int32)
    #         gbi = np.random.randint(0, N, 3, dtype=np.int32)

    #         kb = 5.4
    #         b0 = 2.3

    #         masses = np.random.rand(N)

    #         for lamb_offset in [0, 1]:
    #             for lamb_flag in [0, 1]:

    #                 ref_nrg = jax.partial(
    #                     bonded.centroid_restraint,
    #                     masses=masses,
    #                     group_a_idxs=gai,
    #                     group_b_idxs=gbi,
    #                     kb=kb,
    #                     b0=b0,
    #                     lamb_flag=lamb_flag,
    #                     lamb_offset=lamb_offset
    #                 )

    #                 for lamb_primal in [0.0, 0.1, 0.5, 0.7, 1.0]:

    #                     # we need to clear the du_dp buffer each time, so we need
    #                     # to instantiate test_nrg inside here
    #                     test_nrg = potentials.CentroidRestraint(
    #                         gai,
    #                         gbi,
    #                         masses,
    #                         kb,
    #                         b0,
    #                         lamb_flag,
    #                         lamb_offset,
    #                         precision=precision
    #                     )

    #                     self.compare_forces(
    #                         x_primal,
    #                         lamb_primal,
    #                         x_tangent,
    #                         lamb_tangent,
    #                         ref_nrg,
    #                         test_nrg,
    #                         precision,
    #                         rtol
    #                     )

    #                     # (ytz): we do not compute derivatives w.r.t. centroid restraints. the only one that
    #                     # would make sense would be the force constant. interestingly enough it would act sort
    #                     # as a bias correction term?


    # def test_restraint(self):

    #     B = 8

    #     params = np.random.randn(B, 3)

    #     N = 10
    #     D = 3

    #     b_idxs = []

    #     for _ in range(B):
    #         b_idxs.append(np.random.choice(np.arange(N), size=2, replace=False))

    #     b_idxs = np.array(b_idxs, dtype=np.int32)

    #     lambda_flags = np.random.randint(0, 2, size=(B,))

    #     for precision, rtol in [(np.float32, 2e-5), (np.float64, 1e-9)]:

    #         ref_nrg = jax.partial(
    #             bonded.restraint,
    #             lamb_flags=lambda_flags,
    #             box=None,
    #             bond_idxs=b_idxs
    #         )

    #         ref_nrg_params = jax.partial(
    #             ref_nrg,
    #             params=params
    #         )

    #         x_primal = self.get_random_coords(N, D)
    #         x_tangent = np.random.randn(*x_primal.shape)
    #         lamb_tangent = np.random.rand()

    #         for lamb_primal in [0.0, 0.1, 0.5, 0.7, 1.0]:

    #             # we need to clear the du_dp buffer each time, so we need
    #             # to instantiate test_nrg inside here
    #             test_nrg = potentials.Restraint(
    #                 np.array(b_idxs, dtype=np.int32),
    #                 np.array(params, dtype=np.float64),
    #                 np.array(lambda_flags, dtype=np.int32),
    #                 precision=precision
    #             )

    #             self.compare_forces(
    #                 x_primal,
    #                 lamb_primal,
    #                 x_tangent,
    #                 lamb_tangent,
    #                 ref_nrg_params,
    #                 test_nrg,
    #                 precision,
    #                 rtol
    #             )

    #             primals = (x_primal, lamb_primal, params)
    #             tangents = (x_tangent, lamb_tangent, np.zeros_like(params))

    #             grad_fn = jax.grad(ref_nrg, argnums=(0, 1, 2))
    #             ref_primals, ref_tangents = jax.jvp(grad_fn, primals, tangents)

    #             ref_du_dp_primals = ref_primals[2]
    #             test_du_dp_primals = test_nrg.get_du_dp_primals()
    #             np.testing.assert_almost_equal(ref_du_dp_primals, test_du_dp_primals, rtol)

    #             ref_du_dp_tangents = ref_tangents[2]
    #             test_du_dp_tangents = test_nrg.get_du_dp_tangents()
    #             np.testing.assert_almost_equal(ref_du_dp_tangents, test_du_dp_tangents, rtol)


    def test_harmonic_bond(self):
        np.random.seed(125)

        N = 64
        B = 35
        D = 3

        x = self.get_random_coords(N, D)

        atom_idxs = np.arange(N)
        params = np.random.rand(B, 2).astype(np.float64)
        bond_idxs = []
        for _ in range(B):
            bond_idxs.append(np.random.choice(atom_idxs, size=2, replace=False))
        bond_idxs = np.array(bond_idxs, dtype=np.int32)

        lamb = 0.0

        for precision, rtol in [(np.float32, 4e-5), (np.float64, 1e-9)]:
            test_potential = potentials.HarmonicBond(
                bond_idxs,
                precision=precision
            )

            ref_potential = functools.partial(
                bonded.harmonic_bond,
                bond_idxs=bond_idxs
            )

            x_tangent = np.random.randn(*x.shape)
            lamb_tangent = np.random.rand()

            box = np.eye(3)*100

            self.compare_forces(
                x,
                params,
                box,
                lamb,
                ref_potential,
                test_potential,
                precision,
                rtol
            )

    def test_harmonic_angle(self):
        np.random.seed(125)

        N = 64
        A = 25
        D = 3

        x = self.get_random_coords(N, D)

        atom_idxs = np.arange(N)
        params = np.random.rand(A, 2).astype(np.float64)
        angle_idxs = []
        for _ in range(A):
            angle_idxs.append(np.random.choice(atom_idxs, size=3, replace=False))
        angle_idxs = np.array(angle_idxs, dtype=np.int32)

        lamb = 0.0

        for precision, rtol in [(np.float64, 1e-9), (np.float32, 2e-5)]:
            # print(precision, rtol)
            test_potential = potentials.HarmonicAngle(
                angle_idxs,
                precision=precision
            )

            ref_potential = functools.partial(bonded.harmonic_angle, angle_idxs=angle_idxs)


            x_tangent = np.random.randn(*x.shape)
            lamb_tangent = np.random.rand()

            box = np.eye(3)*100

            self.compare_forces(
                x,
                params,
                box,
                lamb,
                ref_potential,
                test_potential,
                precision,
                rtol
            )


    def test_periodic_torsion(self):
        np.random.seed(125)

        N = 64
        T = 25
        D = 3

        x = self.get_random_coords(N, D)

        atom_idxs = np.arange(N)
        params = np.random.rand(T, 3).astype(np.float64)
        torsion_idxs = []
        for _ in range(T):
            torsion_idxs.append(np.random.choice(atom_idxs, size=4, replace=False))

        torsion_idxs = np.array(torsion_idxs, dtype=np.int32)

        lamb = 0.0

        for precision, rtol in [(np.float32, 2e-5), (np.float64, 1e-9)]:

            test_potential = potentials.PeriodicTorsion(
                torsion_idxs,
                precision=precision
            )

            # test the parameter derivatives for correctness.
            ref_potential = functools.partial(bonded.periodic_torsion, torsion_idxs=torsion_idxs)

            box = np.eye(3)*100

            self.compare_forces(
                x,
                params,
                box,
                lamb,
                ref_potential,
                test_potential,
                precision,
                rtol
            )
