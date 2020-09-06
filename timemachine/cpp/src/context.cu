#include "context.hpp"
#include "gpu_utils.cuh"

namespace timemachine {

Context::Context(
    int N,
    double *x_0,
    double *v_0,
    double *box_0,
    double lambda,
    std::vector<Potential *> potentials,
    std::vector<DualParams *> dual_params) : 
    N_(N),
    potentials_(potentials),
    dual_params_(dual_params),
    lambda_(lambda) {

    d_x_t_ = gpuErrchkCudaMallocAndCopy(x_0, N*3);
    d_v_t_ = gpuErrchkCudaMallocAndCopy(v_0, N*3);
    d_box_t_ = gpuErrchkCudaMallocAndCopy(box_0, 3*3);

    gpuErrchk(cudaMalloc(&d_du_dx_t_, N*3*sizeof(*d_du_dx_t_)));
    gpuErrchk(cudaMalloc(&d_u_t_, 1*sizeof(*d_u_t_)));
    gpuErrchk(cudaMalloc(&d_du_dl_t_, 1*sizeof(*d_du_dl_t_)));

};

Context::~Context() {
    gpuErrchk(cudaFree(d_x_t_));
    gpuErrchk(cudaFree(d_v_t_));
    gpuErrchk(cudaFree(d_box_t_));
    gpuErrchk(cudaFree(d_u_t_));
    gpuErrchk(cudaFree(d_du_dx_t_));
    gpuErrchk(cudaFree(d_du_dl_t_));
};


void Context::compute(unsigned int flags) {

    double *u = (flags & ComputeFlags::u) ? d_u_t_ : nullptr;
    unsigned long long *du_dx = (flags & ComputeFlags::du_dx) ? d_du_dx_t_ : nullptr;
    double *du_dl = (flags & ComputeFlags::du_dl) ? d_du_dl_t_ : nullptr;

    for(int i=0; i < potentials_.size(); i++) {

        DualParams *dp = dual_params_[i];

        // note that dp->d_du_dp itself may be null if the end-user does not care about
        // du_dp.
        double *du_dp = (flags & ComputeFlags::du_dp) ? dp->d_du_dp : nullptr;

        potentials_[i]->execute_device(
            N_,
            dp->size(),
            d_x_t_,
            dp->d_p,
            d_box_t_,
            lambda_,
            du_dx,
            du_dp,
            du_dl,
            u,
            static_cast<cudaStream_t>(0)
        );

    }

};


}