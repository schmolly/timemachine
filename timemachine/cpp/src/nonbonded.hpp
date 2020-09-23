#pragma once

#include "neighborlist.hpp"
#include "potential.hpp"
#include <vector>

namespace timemachine {

template<typename RealType>
class Nonbonded : public Potential {

private:

    int *d_exclusion_idxs_; // [E,2]
    double *d_scales_; // [E, 2]
    int *d_lambda_offset_idxs_;
    int *p_ixn_count_; // pinned memory

    double beta_;
    double cutoff_;
    Neighborlist<RealType> nblist_;

    const int E_;
    const int N_;

    // reduction buffer
    double *d_du_dl_buffer_;
    double *d_u_buffer_;

    int *d_perm_; // hilbert curve permutation

    double *p_coords_; // pinned coordinate for hilbert curve
    double *p_box_; // pinned coordinate for hilbert curve
    int *p_perm_; // pinned coordinate for hilbert curve

    double *d_sorted_x_; //
    double *d_sorted_p_; //
    unsigned long long *d_sorted_du_dx_; //
    double *d_sorted_du_dp_; //

    unsigned long long sort_counter_;

    void hilbert_sort(cudaStream_t stream);

public:

    Nonbonded(
        const std::vector<int> &exclusion_idxs, // [E,2]
        const std::vector<double> &scales, // [E, 2]
        const std::vector<int> &lambda_offset_idxs, // N
        double beta,
        double cutoff
    );

    ~Nonbonded();

    virtual void execute_device(
        const int N,
        const int P,
        const double *d_x,
        const double *d_p,
        const double *d_box,
        const double lambda,
        unsigned long long *d_du_dx,
        double *d_du_dp,
        double *d_du_dl,
        double *d_u,
        cudaStream_t stream
    ) override;



};


}