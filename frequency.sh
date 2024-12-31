#!/usr/bin/env sh

## Governor
cpupower frequency-set --governor performance
#cpupower frequency-set --governor userspace
#cpupower frequency-set --governor powersave

## Frequencies
cpupower frequency-info
cpupower frequency-set -u 3400000
cpupower frequency-set -d 3400000
cpupower frequency-set -f 3400000
#cat /sys/devices/system/cpu/cpu*/cpufreq/scaling_available_frequencies
echo 3400000 | tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_max_freq
cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_max_freq

## Boost
echo "0" | sudo tee /sys/devices/system/cpu/cpufreq/boost
cat /sys/devices/system/cpu/cpu0/cpufreq/boost

## Idle states
#grep . /sys/devices/system/cpu/cpu0/cpuidle/state*/name
#grep . /sys/devices/system/cpu/cpu0/cpuidle/state*/disable
#cpupower idle-info
cpupower idle-set --disable 0
cpupower idle-set --disable 1
cpupower idle-set --disable 2

## Frequency Info
cat /proc/cpuinfo | grep MHz

