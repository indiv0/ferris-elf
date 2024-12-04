#!/bin/sh
./target/release/ferris-elf
#cargo profiler cachegrind --bin ./target/release/ferris-elf -n 10 --sort dr
