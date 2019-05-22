nvcc  --ptxas-options=-v -lineinfo -arch=sm_61 -G -g -Xcompiler -fPIC -I ~/Code/timemachine/timemachine/cpu_functionals/ gpu/custom_bonded_gpu.cu -c

g++ -O3 -march=native -Wall -shared -std=c++11 -fPIC $PLATFORM_FLAGS `python3 -m pybind11 --includes` -L/usr/local/cuda-10.1/lib64/ -I/usr/local/cuda-10.1/include/ wrap_kernels.cpp custom_bonded_gpu.o -o custom_ops`python3-config --extension-suffix` -lcurand -lcublas -lcudart
