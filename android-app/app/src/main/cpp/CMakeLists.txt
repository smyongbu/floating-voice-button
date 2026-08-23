cmake_minimum_required(VERSION 3.22.1)

project(voice_transcribe_runtime LANGUAGES C CXX)

if(POLICY CMP0135)
    cmake_policy(SET CMP0135 NEW)
endif()

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

# transcribe.cpp is pinned to an immutable source archive. The SHA-256 is
# checked before CMake exposes any upstream source to the Android build.
set(TRANSCRIBE_CPP_COMMIT "ea077b87590bcfb090d7c38c03ab36cd1c7005d3")
set(TRANSCRIBE_CPP_ARCHIVE_SHA256 "577826A626C85BD07E40EFADA8F9578BC2689132F14AD41B71EE496D9A9711D8")

set(TRANSCRIBE_BUILD_TESTS OFF CACHE BOOL "" FORCE)
set(TRANSCRIBE_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
set(TRANSCRIBE_BUILD_TOOLS OFF CACHE BOOL "" FORCE)
set(TRANSCRIBE_BUILD_SHARED OFF CACHE BOOL "" FORCE)
set(TRANSCRIBE_INSTALL OFF CACHE BOOL "" FORCE)
set(TRANSCRIBE_USE_OPENMP OFF CACHE BOOL "" FORCE)
set(TRANSCRIBE_USE_SYSTEM_BLAS OFF CACHE BOOL "" FORCE)
set(TRANSCRIBE_METAL OFF CACHE BOOL "" FORCE)
set(TRANSCRIBE_VULKAN OFF CACHE BOOL "" FORCE)
set(TRANSCRIBE_CUDA OFF CACHE BOOL "" FORCE)
set(TRANSCRIBE_HIP OFF CACHE BOOL "" FORCE)
set(TRANSCRIBE_GGML_BACKEND_DL OFF CACHE BOOL "" FORCE)
set(GGML_NATIVE OFF CACHE BOOL "" FORCE)
set(GGML_OPENMP OFF CACHE BOOL "" FORCE)
set(GGML_BACKEND_DL OFF CACHE BOOL "" FORCE)
set(GGML_CPU_ALL_VARIANTS OFF CACHE BOOL "" FORCE)
set(GGML_CPU_KLEIDIAI OFF CACHE BOOL "" FORCE)

include(FetchContent)
FetchContent_Declare(
    transcribe_cpp
    URL "https://github.com/handy-computer/transcribe.cpp/archive/${TRANSCRIBE_CPP_COMMIT}.tar.gz"
    URL_HASH "SHA256=${TRANSCRIBE_CPP_ARCHIVE_SHA256}"
)
FetchContent_MakeAvailable(transcribe_cpp)

# The pinned upstream revision uses CMAKE_SOURCE_DIR for this one build-tree
# include path. Restore the correct subproject path when it is embedded here.
target_include_directories(transcribe PUBLIC "${transcribe_cpp_SOURCE_DIR}/include")

add_library(
    transcribe_jni
    SHARED
    transcribe_jni.cpp
)

target_include_directories(
    transcribe_jni
    PRIVATE
    "${transcribe_cpp_SOURCE_DIR}/include"
)

target_compile_options(
    transcribe_jni
    PRIVATE
    -O3
    -fvisibility=hidden
    -fvisibility-inlines-hidden
    -ffunction-sections
    -fdata-sections
)

target_link_options(
    transcribe_jni
    PRIVATE
    -Wl,--gc-sections
    -Wl,-z,max-page-size=16384
)

find_library(ANDROID_LOG_LIBRARY log)
find_library(ANDROID_LIBRARY android)
target_link_libraries(
    transcribe_jni
    PRIVATE
    transcribe
    "${ANDROID_LOG_LIBRARY}"
    "${ANDROID_LIBRARY}"
)
