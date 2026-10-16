cmake_minimum_required(VERSION 3.22)
project(zb_load_trace_tests LANGUAGES C CXX ASM)
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
get_filename_component(ZB_SOURCE "${CMAKE_CURRENT_SOURCE_DIR}/../.." ABSOLUTE)
add_compile_definitions(FMT_CONSTEVAL=)
set(DYNARMIC_FRONTENDS "A32" CACHE STRING "" FORCE)
set(DYNARMIC_TESTS OFF CACHE BOOL "" FORCE)
set(DYNARMIC_WARNINGS_AS_ERRORS OFF CACHE BOOL "" FORCE)
set(DYNARMIC_USE_BUNDLED_EXTERNALS ON CACHE BOOL "" FORCE)
set(DYNARMIC_USE_PRECOMPILED_HEADERS OFF CACHE BOOL "" FORCE)
add_subdirectory("${ZB_SOURCE}/third_party/dynarmic" dynarmic EXCLUDE_FROM_ALL)
add_library(diagnostic_core STATIC
    "${ZB_SOURCE}/core/src/guest_thread.cpp"
    "${ZB_SOURCE}/core/src/guest_memory.cpp"
    "${ZB_SOURCE}/core/src/cp15.cpp"
    "${ZB_SOURCE}/core/src/log.cpp"
    "${ZB_SOURCE}/core/src/runtime_report.cpp"
    "${ZB_SOURCE}/core/src/hang_watchdog.cpp"
    platform_stubs.cpp)
target_include_directories(diagnostic_core PUBLIC "${ZB_SOURCE}/core/include" "${ZB_SOURCE}/tests/host")
target_link_libraries(diagnostic_core PUBLIC dynarmic pthread)
add_executable(trace_guest_thread_test trace_guest_thread_test.cpp)
target_link_libraries(trace_guest_thread_test PRIVATE diagnostic_core)
add_executable(hang_watchdog_test "${ZB_SOURCE}/tests/host/hang_watchdog_test.cpp")
target_link_libraries(hang_watchdog_test PRIVATE diagnostic_core)
enable_testing()
add_test(NAME trace_guest_thread_test COMMAND trace_guest_thread_test)
add_test(NAME hang_watchdog_test COMMAND hang_watchdog_test)
