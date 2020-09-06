#pragma once

#include <vector>
// #include "potential.hpp"
#include "integrator.hpp"
#include "bound_potential.hpp"
#include "observable.hpp"

namespace timemachine {

class Context {

public:

    Context(
        int N,
        const double *x_0,
        const double *v_0,
        const double *box_0,
        double lambda,
        std::vector<BoundPotential *> bps,
        Integrator *intg
    );

    ~Context();

    void step();

    int num_atoms() const;

    void get_du_dx_t(unsigned long long *out_buffer) const;

    void get_x_t(double *out_buffer) const;

    void get_v_t(double *out_buffer) const;

private:

    // compute u, du/dx, du/dp, du/dl as needed
    // this does *not* clear the buffer

    // void clear_internals(unsigned int flags) {
    //     if(flags & ComputeFlags::u) {
    //         gpuErrchk(cudaMemset(x_u_t_, 0, 1*sizeof(*u)));
    //     }
    //     if(flags & ComputeFlags::du_dx) {
    //         gpuErrchk(cudaMemset(d_du_dx_t_, 0, N_*3*sizeof(*d_du_dx_t_)));
    //     }
    //     if(flags & ComputeFlags::du_dl) {
    //         gpuErrchk(cudaMemset(d_du_dl_t_, 0, 1*sizeof(*du_dl_t_)));
    //     }

    //     if(flags & ComputeFlags::du_dp) {
    //         for(int i=0; i < d_partial_pots_.size(); i++) {
    //             d_partial_pots_.clear_du_dp();
    //             // gpuErrchk(cudaMemset(d_du_dp_t_, 0, P_*sizeof(*d_du_dp_t_)));                
    //         }
    //     }
    // }

    void compute(unsigned int flags);

    int step_;
    int N_; // number of particles

    double *d_x_t_; // coordinates
    double *d_v_t_; // velocities
    double *d_box_t_; // box vectors
    double *d_u_t_; // u (energy)
    double lambda_; // (ytz): not a pointer!

    unsigned long long *d_du_dx_t_; // du/dx 

    Integrator *intg_;
    std::vector<Observable *> observables_;
    std::vector<BoundPotential *> bps_;


};

}