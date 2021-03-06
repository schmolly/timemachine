import numpy as np
from timemachine.integrator import langevin_coefficients

class System():

    def __init__(self, x0, v0, box, potentials, integrator_args):
        self.x0 = x0
        self.v0 = v0
        self.box = box
        self.potentials = potentials
        self.integrator_args = integrator_args


# class Integrator():

#     def __init__(self, steps, dt, temperature, friction, masses, seed):

#         # minimization_steps = 2000

#         ca, cbs, ccs = langevin_coefficients(
#             temperature,
#             dt,
#             friction,
#             masses
#         )

#         complete_cas = np.ones(steps)*ca
#         complete_dts = np.concatenate([
#             np.linspace(0, dt, minimization_steps),
#             np.ones(steps-minimization_steps)*dt
#         ])

#         self.dts = complete_dts
#         self.cas = complete_cas
#         self.cbs = -cbs
#         self.ccs = ccs
#         # self.lambs = np.zeros(steps) + lamb
#         self.seed = seed