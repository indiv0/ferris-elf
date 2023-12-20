#![feature(portable_simd)]

use std::{
    hint::black_box,
    time::{Duration, Instant},
};

trait IntoInput<T: Copy> {
    fn into_input(self) -> T;
}

impl<T: Copy> IntoInput<T> for T {
    fn into_input(self) -> T {
        self
    }
}

impl IntoInput<&[u8]> for Vec<u8> {
    fn into_input(self) -> &'static [u8] {
        self.leak()
    }
}

impl IntoInput<&str> for Vec<u8> {
    fn into_input(self) -> &'static str {
        std::str::from_utf8(self.leak()).unwrap()
    }
}

fn main() {
    let input = std::env::var("INPUT").expect("No input file provided");
    // let input = input.split(',').map(|s| s.parse().unwrap()).collect::<Vec<u8>>();
    // let input = std::fs::read("input.txt").unwrap();
    let (ans, mut times) = benchmark(input.into_bytes());

    times.sort();
    
    println!("FERRIS_ELF_ANSWER {}", ans);
    println!("FERRIS_ELF_MEDIAN {}", times[50].as_nanos());
    println!("FERRIS_ELF_AVERAGE {}", times.iter().sum::<Duration>().as_nanos() / 100);
    println!("FERRIS_ELF_MIN {}", times.iter().min().unwrap_or(&Duration::ZERO).as_nanos());
    println!("FERRIS_ELF_MAX {}", times.iter().max().unwrap_or(&Duration::ZERO).as_nanos());
}

fn benchmark(input: Vec<u8>) -> (String, [Duration; 100]) {
    let input = input.into_input();

    let mut warmup_iters = 1;

    let answer = format!("{}", ferris_elf::run(input));

    println!("Answer: {}, warming up for 5 sec...", answer);

    // Warm up the CPU etc for 5 seconds
    let warmup_start = Instant::now();
    while warmup_start.elapsed() < Duration::from_secs(5) {
        if format!("{}", black_box(ferris_elf::run(black_box(input)))) != answer {
            panic!("Solution returned two different answers on same input!")
        }
        warmup_iters += 1;
    }

    let estimated_dur = Duration::from_secs(5) / warmup_iters;
    println!("Estimated duration per run: {:?}. Running {} iterations...", estimated_dur, warmup_iters);

    let iters = (warmup_iters / 100).max(1);

    // Times for eacha batch
    let mut times = [Duration::ZERO; 100];

    // Benchmark in 100 batches
    let mut start = Instant::now();
    for sample in 0..100 {
        for _ in 0..iters {
            let _ = black_box(ferris_elf::run(black_box(input)));
        }

        // Record this batch
        let elapsed = start.elapsed();
        times[sample] = elapsed / iters;
        start += elapsed;
    }

    println!("Benchmark complete: {:#?}", times);

    (answer, times)
}
