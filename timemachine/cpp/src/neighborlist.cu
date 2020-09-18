#include <vector>
#include <iostream>

#include "neighborlist.hpp"
#include "k_find_block_bounds.cuh"
#include "gpu_utils.cuh"

#include "cudaProfiler.h"
#include "cuda_profiler_api.h"

namespace timemachine {

template<typename RealType>
Neighborlist<RealType>::Neighborlist(
	int N,
	int D) {

    int tpb = 32;
    int B = (N+tpb-1)/tpb;

    gpuErrchk(cudaMalloc(&d_block_bounds_ctr_, B*D*sizeof(*d_block_bounds_ctr_)));
    gpuErrchk(cudaMalloc(&d_block_bounds_ext_, B*D*sizeof(*d_block_bounds_ext_)));

}

template<typename RealType>
Neighborlist<RealType>::~Neighborlist() {

    gpuErrchk(cudaFree(d_block_bounds_ctr_));
    gpuErrchk(cudaFree(d_block_bounds_ext_));

}


bool is_pow_2(int x) {
    return (x & (x - 1)) == 0;
}

int log2_int(int v) {
    int bits = 0;
    while (v >>= 1) ++bits;
    return bits;
}

int pow_int(int x, int p) {
  if (p == 0) return 1;
  if (p == 1) return x;

  int tmp = pow_int(x, p/2);
  if (p%2 == 0) return tmp * tmp;
  else return x * tmp * tmp;
}

template<typename RealType>
void Neighborlist<RealType>::compute_block_bounds_cpu(
    const int N,
    const int D,
    const int block_size,
    const double *h_coords,
    const double *h_box,
    double *bb_ctrs,
    double *bb_exts) {
   

    int num_blocks = (N + block_size - 1)/block_size;

    for(int block_idx = 0; block_idx < num_blocks; block_idx++) {
        for(int d=0; d < D; d++) {
            double width = h_box[d*3+d];
            double ci_min =  9999999;
            double ci_max = -9999999;
            for(int i=0; i < block_size; i++) {
                int tid = block_idx*block_size + i;
                if(tid < N) {
                    // int atom_idx = perm[tid];
                    int atom_idx = tid;
                    double ci = h_coords[atom_idx*D + d];
                    ci -= width*floor(ci/width); // move to home box
                    ci_min = ci < ci_min ? ci : ci_min;
                    ci_max = ci > ci_max ? ci : ci_max;
                }
            }
         
            // printf("dim %d block_idx %d ctr %f ext %f\n", d, block_idx, (ci_max + ci_min)/2.0, ci_max - ci_min);
            bb_ctrs[block_idx*D+d] = (ci_max + ci_min)/2.0;
            bb_exts[block_idx*D+d] = (ci_max - ci_min)/2.0;
        }
    }

}

template<typename RealType>
std::vector<std::vector<int> > Neighborlist<RealType>::build_nblist_mpu(
    int N,
    int D,
    const double *h_coords,
    const double *h_box,
    const double cutoff) {

    double *d_coords = gpuErrchkCudaMallocAndCopy(h_coords, N*D*sizeof(double));
    double *d_box = gpuErrchkCudaMallocAndCopy(h_box, D*D*sizeof(double));    

    this->compute_block_bounds(
        N,
        D,
        d_coords,
        d_box,
        static_cast<cudaStream_t>(0)
    );

    unsigned int *d_ixn_count;
    gpuErrchk(cudaMalloc(&d_ixn_count, 1*sizeof(*d_ixn_count)));
    gpuErrchk(cudaMemset(d_ixn_count, 0, 1*sizeof(*d_ixn_count)));
    // *d_ixn_count = 0;
    const int B = (N+32-1)/32;
    unsigned long long MAX_TILE_BUFFER = B*B;
    unsigned long long MAX_ATOM_BUFFER = B*10000;
    int *d_ixn_tiles;
    gpuErrchk(cudaMalloc(&d_ixn_tiles, MAX_TILE_BUFFER*sizeof(*d_ixn_tiles)));
    unsigned int *d_ixn_atoms;
    gpuErrchk(cudaMalloc(&d_ixn_atoms, MAX_ATOM_BUFFER*sizeof(*d_ixn_atoms)));

    int tpb = 32;

    const int Y = (B+32-1)/32;

    unsigned int *d_trim_atoms;

    gpuErrchk(cudaMalloc(&d_trim_atoms, B*Y*32*sizeof(*d_trim_atoms)));

    // std::cout << "Grid sizes: " << B << " " << (B+32-1)/32 << std::endl;
    dim3 dimGrid(B, Y, 1); // block x, y, z dims


    std::vector<float> h_coords_f32(N*D);
    for(int i=0; i < N*D; i++) {
        h_coords_f32[i] = h_coords[i];
    }

    std::cout << "A" << std::endl;

    // float *d_coords_f32 = gpuErrchkCudaMallocAndCopy(&h_coords_f32[0], N*D);


    std::cout << "B" << std::endl;

    // cudaProfilerStart();
    // (ytz): TBD shared memory, stream
    find_blocks_with_interactions<RealType><<<dimGrid, tpb>>>(
        N,
        d_block_bounds_ctr_,
        d_block_bounds_ext_,
        d_coords,
        d_box,
        d_ixn_count,
        d_ixn_tiles,
        d_ixn_atoms,
        d_trim_atoms,
        cutoff
    );

    std::cout << "C" << std::endl;

    cudaDeviceSynchronize();

    // cudaProfilerStop();

    std::cout << "D" << std::endl;

    // (ytz): TBD shared memory, stream
    compact_trim_atoms<<<B, tpb>>>(
        N,
        Y,
        d_trim_atoms,
        d_ixn_count,
        d_ixn_tiles,
        d_ixn_atoms
    );
    gpuErrchk(cudaPeekAtLastError());


    cudaDeviceSynchronize();

    // std::cout << "A" << std::endl;


    unsigned int h_ixn_count;
    gpuErrchk(cudaMemcpy(&h_ixn_count, d_ixn_count, 1*sizeof(*d_ixn_count), cudaMemcpyDeviceToHost));

    // std::cout << "B" << std::endl;

    std::vector<int> h_ixn_tiles(MAX_TILE_BUFFER);
    std::vector<unsigned int> h_ixn_atoms(MAX_ATOM_BUFFER);

    gpuErrchk(cudaMemcpy(&h_ixn_tiles[0], d_ixn_tiles, MAX_TILE_BUFFER*sizeof(int), cudaMemcpyDeviceToHost));
    gpuErrchk(cudaMemcpy(&h_ixn_atoms[0], d_ixn_atoms, MAX_ATOM_BUFFER*sizeof(unsigned int), cudaMemcpyDeviceToHost));

    // unsigned long long MAX_TILE_BUFFER = (N/32)*(N/32);
    // unsigned long long MAX_ATOM_BUFFER = (N/32)*10000;
    // int *h_ixn_tiles;
    // gpuErrchk(cudaMalloc(&d_ixn_tiles, MAX_TILE_BUFFER*sizeof(*d_ixn_tiles)));
    // unsigned int *h_ixn_atoms;
    // gpuErrchk(cudaMalloc(&d_ixn_atoms, MAX_ATOM_BUFFER*sizeof(*d_ixn_atoms)));

    // for(int i=0; i < h_ixn_tiles.size(); i++) {
        // std::cout << i << " " << h_ixn_tiles << std::endl;
    // }

    std::vector<std::vector<int> > ixn_list(B, std::vector<int>());

    // std::cout << "IXN COUNT:" << h_ixn_count << std::endl;
    // std::cout << "SIZE OF IXN_LIST: " << ixn_list.size() << std::endl;

    for(int i=0; i < h_ixn_count; i++) {
        int tile_idx = h_ixn_tiles[i];
        // std::cout << "tile_idx: " << tile_idx << std::endl;
        // std::cout << "i: " << i << " tile_idx: " << tile_idx << std::endl;
        for(int j=0; j < 32; j++) {
            // std::cout << "j: " << j << std::endl;
            int atom_j_idx = h_ixn_atoms[i*32+j];
            // std::cout << "atom_j_idx: " << atom_j_idx << std::endl;
            if(atom_j_idx < N) {
                // std::cout << "push_back: " << atom_j_idx << " " << std::endl;
                ixn_list[tile_idx].push_back(atom_j_idx);
            }
        }
    }

    // std::cout << "E" << std::endl;

    // for(int i=0; i < B; i++) {
    //     for(int j=0; j < Y*32; j++) {
    //         int ixn_atom = dh_trim_atoms[i*Y*32+j];
    //         if(ixn_atom < N) {
    //             // std::cout << "adding into " << i << " with " << ixn_atom << std::endl;
    //             ixn_list[i].push_back(ixn_atom);                
    //         }
    //     }
    // }



    gpuErrchk(cudaFree(d_coords));
    // gpuErrchk(cudaFree(d_coords_f32));
    gpuErrchk(cudaFree(d_box));
    gpuErrchk(cudaFree(d_ixn_count));
    gpuErrchk(cudaFree(d_ixn_tiles));
    gpuErrchk(cudaFree(d_ixn_atoms));
    gpuErrchk(cudaFree(d_trim_atoms));

    return ixn_list;

}

template<typename RealType>
std::vector<std::vector<int> >  Neighborlist<RealType>::build_nblist_cpu(
    int N,
    int D,
    const double *h_coords,
    const double *h_box,
    const double cutoff) {
    /*
    Reference neighborlist algorithm:
    Given N atoms, we subdivide into blocks of size 2^B log_2(N) times.


    Suppose we have 256 atoms. We compute block bounds in groups of
    128, 64, 32, 16, 8, 4, 2, 1. In the limit as the group size == 1 we have the
    coordinates themselves.

    We proceed by

    128x128
    64x64
    32x32
    32x16
    32x8
    32x4
    32x2
    32x1

    When we're finally down to 32x1 we do a full check
   
    */

    // std::cout << log2_int(31) << std::endl;
    // std::cout << log2_int(32) << std::endl;
    // std::cout << log2_int(33) << std::endl;

    // throw std::runtime_error("N is not a power of 2.");

    // if(!is_pow_2(N)) {
    //     throw std::runtime_error("N is not a power of 2.");
    // }

    int row_block_size = N;
    int col_block_size = N;

    //
    // 2^0 = 1
    // 2^1 = 2
    // 2^2 = 4
    // 2^3 = 8
    // 2^4 = 16     
    // 2^5 = 32    num_rounds == 6
    int num_rounds = log2_int(N) + 1;
    num_rounds = max(num_rounds, 6); // need at least 6 rounds

    std::vector<std::vector<double> > all_block_ctrs;
    std::vector<std::vector<double> > all_block_exts;

    // compute block bounds t
    for(int round=0; round < num_rounds; round++)  {
        int block_size = pow_int(2, round);
        int num_blocks = (N + block_size - 1)/block_size;

        std::vector<double> bb_ctrs(num_blocks*3);
        std::vector<double> bb_exts(num_blocks*3);
        this->compute_block_bounds_cpu(
            N,
            D,
            block_size,
            h_coords,
            h_box,
            &bb_ctrs[0],
            &bb_exts[0]
        );

        all_block_ctrs.push_back(bb_ctrs);
        all_block_exts.push_back(bb_exts);

    }

    const int num_blocks_of_32 = (N + 32 - 1) / 32;

    const int bound_idx_32 = log2_int(32);
    // implement OpenMM's bbox approach

    std::vector<std::vector<int> > ixn_list;

    int dist_calcs = 0;

    double bx = h_box[0*3+0];
    double by = h_box[1*3+1];
    double bz = h_box[2*3+2];

    for(int rbidx=0; rbidx < num_blocks_of_32; rbidx++) {

        double box_ctr_x = all_block_ctrs[bound_idx_32][rbidx*3+0];
        double box_ctr_y = all_block_ctrs[bound_idx_32][rbidx*3+1];
        double box_ctr_z = all_block_ctrs[bound_idx_32][rbidx*3+2];

        double box_ext_x = all_block_exts[bound_idx_32][rbidx*3+0];
        double box_ext_y = all_block_exts[bound_idx_32][rbidx*3+1];
        double box_ext_z = all_block_exts[bound_idx_32][rbidx*3+2];

        std::vector<int> interacting_idxs;

        for(int bj=0; bj < num_blocks_of_32; bj++) {
            int j_start = bj*32;
            int j_end = min((bj+1)*32, N);

            double bj_ctr_x = all_block_ctrs[bound_idx_32][bj*3+0];
            double bj_ctr_y = all_block_ctrs[bound_idx_32][bj*3+1];
            double bj_ctr_z = all_block_ctrs[bound_idx_32][bj*3+2];

            double bj_ext_x = all_block_exts[bound_idx_32][bj*3+0];
            double bj_ext_y = all_block_exts[bound_idx_32][bj*3+1];
            double bj_ext_z = all_block_exts[bound_idx_32][bj*3+2];

            double dx = box_ctr_x - bj_ctr_x;
            double dy = box_ctr_y - bj_ctr_y;
            double dz = box_ctr_z - bj_ctr_z;

            dx -= bx*floor(dx/bx+0.5);
            dy -= by*floor(dy/by+0.5);
            dz -= bz*floor(dz/bz+0.5);

            dx = max(0.0, fabs(dx) - box_ext_x - bj_ext_x);
            dy = max(0.0, fabs(dy) - box_ext_y - bj_ext_y);
            dz = max(0.0, fabs(dz) - box_ext_z - bj_ext_z);

            double box_box_dist = sqrt(dx*dx + dy*dy + dz*dz);

            if(box_box_dist > cutoff) {
                continue;
            }

            dist_calcs += 1;

            for(int j=j_start; j < j_end; j++) {

                double jx = h_coords[j*3+0];
                double jy = h_coords[j*3+1];
                double jz = h_coords[j*3+2];

                double dx = box_ctr_x - jx;
                double dy = box_ctr_y - jy;
                double dz = box_ctr_z - jz;

                dx -= bx*floor(dx/bx+0.5);
                dy -= by*floor(dy/by+0.5);
                dz -= bz*floor(dz/bz+0.5);

                dx = max(0.0, fabs(dx) - box_ext_x);
                dy = max(0.0, fabs(dy) - box_ext_y);
                dz = max(0.0, fabs(dz) - box_ext_z);

                double box_dist = sqrt(dx*dx + dy*dy + dz*dz);
                dist_calcs += 1;

                int row_start = rbidx*32;
                int row_end = min((rbidx+1)*32, N);

                if(box_dist > cutoff) {
                    continue;
                }

                bool keep = false;
                
                for(int i=row_start; i < row_end; i++) {

                    double ix = h_coords[i*3+0];
                    double iy = h_coords[i*3+1];
                    double iz = h_coords[i*3+2];

                    double dx = ix - jx;
                    double dy = iy - jy;
                    double dz = iz - jz;

                    dx -= bx*floor(dx/bx+0.5);
                    dy -= by*floor(dy/by+0.5);
                    dz -= bz*floor(dz/bz+0.5);

                    double atom_dist = sqrt(dx*dx + dy*dy + dz*dz);
                    dist_calcs += 1;

                    if(atom_dist < cutoff) {
                        keep = true;
                        break;
                    }
                }

                if(keep) {
                    interacting_idxs.push_back(j);
                }

            }

        }

        // for(int j=0; j < N; j++) {

        // }

        ixn_list.push_back(interacting_idxs);

    }

    std::cout << "distance calcs: " << dist_calcs << "/" << N*N << " ratio: " << dist_calcs/(N*N) << std::endl;

    return ixn_list;

}

template <typename RealType>
void Neighborlist<RealType>::compute_block_bounds(
	int N,
	int D,
	const double *d_coords,
    const double *d_box,
    // const int *d_perm,
	cudaStream_t stream) {

    int tpb = 32;
    int B = (N+tpb-1)/tpb; // total number of blocks we need to process

    gpuErrchk(cudaMemsetAsync(d_block_bounds_ctr_, 0, B*D*sizeof(*d_block_bounds_ctr_), stream));
    gpuErrchk(cudaMemsetAsync(d_block_bounds_ext_, 0, B*D*sizeof(*d_block_bounds_ext_), stream));

    k_find_block_bounds<<<B, tpb, 0, stream>>>(
        N,
        D,
        B,
        d_coords,
        d_box,
        // perm,
        d_block_bounds_ctr_,
        d_block_bounds_ext_
    );	

    gpuErrchk(cudaPeekAtLastError());

};


template class Neighborlist<double>;
template class Neighborlist<float>;


}