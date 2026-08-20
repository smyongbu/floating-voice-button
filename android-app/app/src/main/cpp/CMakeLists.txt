cmake_minimum_required(VERSION 3.22.1)

project(voice_whisper_acft LANGUAGES C CXX)

if(POLICY CMP0135)
    cmake_policy(SET CMP0135 NEW)
endif()

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

# whisper.cpp is fetched from one immutable upstream commit. The archive hash
# makes a changed or corrupted download fail before any native code is built.
set(WHISPER_CPP_COMMIT "306c88f4d1286aec1bf96e544632897886af5501")
set(WHISPER_CPP_ARCHIVE_SHA256 "f3585ebf64df3e41b26c45d93bdb38b423ca1de0bf40cc4b6d320254867a75df")

include(FetchContent)
FetchContent_Declare(
    whisper_cpp
    URL "https://github.com/ggml-org/whisper.cpp/archive/${WHISPER_CPP_COMMIT}.tar.gz"
    URL_HASH "SHA256=${WHISPER_CPP_ARCHIVE_SHA256}"
)
FetchContent_GetProperties(whisper_cpp)
if(NOT whisper_cpp_POPULATED)
    FetchContent_Populate(whisper_cpp)
endif()

# Mirror the official whisper.cpp Android example: compile whisper.cpp into
# this app's single JNI library and reuse the bundled ggml CMake project.
set(BUILD_SHARED_LIBS OFF CACHE BOOL "" FORCE)
set(GGML_NATIVE OFF CACHE BOOL "" FORCE)
set(GGML_OPENMP OFF CACHE BOOL "" FORCE)
set(GGML_BACKEND_DL OFF CACHE BOOL "" FORCE)
set(GGML_CPU_ALL_VARIANTS OFF CACHE BOOL "" FORCE)
set(GGML_CPU_KLEIDIAI OFF CACHE BOOL "" FORCE)

FetchContent_Declare(ggml SOURCE_DIR "${whisper_cpp_SOURCE_DIR}/ggml")
FetchContent_MakeAvailable(ggml)

add_library(
    whisper_acft_jni
    SHARED
    whisper_acft_jni.cpp
    "${whisper_cpp_SOURCE_DIR}/src/whisper.cpp"
)

target_include_directories(
    whisper_acft_jni
    PRIVATE
    "${whisper_cpp_SOURCE_DIR}/include"
    "${whisper_cpp_SOURCE_DIR}/src"
    "${whisper_cpp_SOURCE_DIR}/ggml/include"
    "${whisper_cpp_SOURCE_DIR}/ggml/src"
    "${whisper_cpp_SOURCE_DIR}/ggml/src/ggml-cpu"
)

target_compile_definitions(
    whisper_acft_jni
    PRIVATE
    GGML_USE_CPU
    WHISPER_VERSION="1.9.2"
)

target_compile_options(
    whisper_acft_jni
    PRIVATE
    -O3
    -fvisibility=hidden
    -fvisibility-inlines-hidden
    -ffunction-sections
    -fdata-sections
)

target_link_options(
    whisper_acft_jni
    PRIVATE
    -Wl,--gc-sections
    -Wl,-z,max-page-size=16384
)

find_library(ANDROID_LOG_LIBRARY log)
find_library(ANDROID_LIBRARY android)
target_link_libraries(
    whisper_acft_jni
    PRIVATE
    ggml
    "${ANDROID_LOG_LIBRARY}"
    "${ANDROID_LIBRARY}"
)
