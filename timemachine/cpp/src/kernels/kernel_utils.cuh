#pragma once

#include <cstdio>
#define WARP_SIZE 32

#define HESS_3N3N(i,j,N,di,dj) (di*N*3*N + i*3*N + dj*N + j)
#define HESS_N3N3(i,j,N,di,dj) (i*3*N*3 + di*N*3 + j*3 + dj)
#define HESS_IDX HESS_N3N3

#define HESS_NDND(i,j,N,di,dj,D) (i*D*N*D + di*N*D + j*D + dj)
// dimensions first

// these are dimension major, atom minor, x0x1..xn, y0y1...yn, z0z1...zn, etc
// #define HESS_NDND(i,j,N,di,dj,D) (di*N*D*N + i*D*N + dj*N + j)
#define HESS_IDX_ND HESS_NDND

// inline __device__ int HESS_IDX_ND(int i, int j, int N, int di, int dj, int D) {
//     int DN = D*N;
//     int ii = di*N+i;
//     int jj = dj*N+j;
//     if(ii < jj) {
//         int tmp = jj;
//         jj = ii;
//         ii = tmp;
//     }
//     return ii*DN + jj;
// }

#define MP_IDX_ND(p,i,N,d,D) (p*N*D + i*D + d)

// #define MP_IDX_ND(p,i,N,d,D) (p*D*N + d*N + i)

#define ONE_4PI_EPS0 138.935456

inline __device__ int linearize(int i, int j, int d) {
    return d*(d-1)/2 - (d-i) * (d-i-1)/2 +j;
}

// inline __device__ float gpuSqrt(float arg) {
//   return sqrtf(arg);
// }

// inline __device__ double gpuSqrt(double arg) {
//   return sqrt(arg);
// }


inline __device__ float real_sqrt(const float x) {
    return sqrtf(x);
}

inline __device__ double real_sqrt(const double x) {
    return sqrt(x);
}

inline __device__ float real_exp(const float x) {
    return expf(x);
}

inline __device__ double real_exp(const double x) {
    return exp(x);
}

inline __device__ float real_erfc(const float x) {
    return erfcf(x);
}

inline __device__ double real_erfc(const double x) {
    return erfc(x);
}


template<typename RealType, int D>
inline __device__ RealType fast_vec_rnorm(const RealType v[D]);

template<>
inline __device__ float fast_vec_rnorm<float, 3>(const float v[3]) {
    return rnorm3df(v[0], v[1], v[2]);
};

template<>
inline __device__ double fast_vec_rnorm<double, 3>(const double v[3]) {
    return rnorm3d(v[0], v[1], v[2]);
};

template<>
inline __device__ float fast_vec_rnorm<float, 4>(const float v[4]) {
    return rnorm4df(v[0], v[1], v[2], v[3]);
};

template<>
inline __device__ double fast_vec_rnorm<double, 4>(const double v[4]) {
    return rnorm4d(v[0], v[1], v[2], v[3]);
};

template<typename RealType, int D>
inline __device__ RealType fast_vec_norm(const RealType v[D]);

template<>
inline __device__ float fast_vec_norm<float, 3>(const float v[3]) {
    return norm3df(v[0], v[1], v[2]);
};

template<>
inline __device__ double fast_vec_norm<double, 3>(const double v[3]) {
    return norm3d(v[0], v[1], v[2]);
};

template<>
inline __device__ float fast_vec_norm<float, 4>(const float v[4]) {
    return norm4df(v[0], v[1], v[2], v[3]);
};

template<>
inline __device__ double fast_vec_norm<double, 4>(const double v[4]) {
    return norm4d(v[0], v[1], v[2], v[3]);
};
