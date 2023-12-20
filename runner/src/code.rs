use std::collections::HashMap;

#[derive(Clone)]
pub struct Valve {
    rate: i64,
    connections: Vec<u16>,
    open: bool,
}
type Valves = HashMap<u16, Valve>;

const AA: u16 = ((b'A' as u16) << 8) | (b'A' as u16);

#[inline]
pub fn parse(input: &str) -> Valves {
    input
        .lines()
        .map(|sline| {
            let line = sline.as_bytes();
            // If not for the different text when a valve only has a single tunnel,
            // this wouldn't be necessary. But the different text does three things:
            // 1) removes an s from tunnels (net -1)
            // 2) adds an s to lead (net 0)
            // 3) removes an s from valves (net -1)
            // This means that the tunnel list can start at positions:
            // 50 => 2 digit flow value, multiple tunnels. Char 48 is always an `s`
            // 49 => 1 digit flow value, multiple tunnels. Char 48 is always a space
            // 49 => 2 digit flow value, one tunnel. Char 48 is always a space
            // 48 => 1 digit flow value, one tunnel. Char 48 is a capital A-Z.
            let tunnels = match line[48] {
                b's' => 50,
                b' ' => 49,
                _ => 48,
            };
            (
                line[6..8].iter().fold(0, |a, b| (a << 8) | *b as u16),
                Valve {
                    rate: line[23..25].iter().fold(0, |a, b| match b {
                        b';' => a,
                        _ => (10 * a) + (b - b'0') as i64,
                    }),
                    connections: line[tunnels..]
                        .split(|byte| b','.eq(byte) || b' '.eq(byte))
                        .filter(|slc| slc.len() > 0)
                        .map(|valve| valve.iter().fold(0, |a, b| (a << 8) | *b as u16))
                        .collect(),
                    open: false,
                },
            )
        })
        .collect()
}

pub fn double_valverun(
    human: (u16, u16),
    elephant: (u16, u16),
    valves: &Valves,
    time: i64,
    highest: &mut HashMap<i64, i64>,
    total: i64,
    turnflow: i64,
) -> i64 {
    if time == 0 {
        return total;
    }

    let best_time = match highest.get(&time) {
        Some(&score) => score,
        _ => 0,
    };
    // Same as p1. Works for the test input & my own input.
    if best_time > (total + 26) {
        return 0;
    }
    if total > best_time {
        highest.insert(time, total);
    }

    let mut curmax = total;
    let (hum_current, hum_last) = human;
    let (ele_current, ele_last) = elephant;
    let mut hum_valve = valves.get(&hum_current).unwrap().clone();
    let mut ele_valve = valves.get(&ele_current).unwrap().clone();
    let hum_conns = hum_valve.connections.clone();
    let ele_conns = ele_valve.connections.clone();

    // Both closed and positive flow available? Run both!
    if !hum_valve.open
        && hum_valve.rate > 0
        && !ele_valve.open
        && ele_valve.rate > 0
        && hum_current != ele_current
    {
        hum_valve.open = true;
        ele_valve.open = true;
        let rate = ele_valve.rate + hum_valve.rate;
        let mut cloned = valves.clone();
        cloned.insert(ele_current, ele_valve);
        cloned.insert(hum_current, hum_valve);
        curmax = curmax.max(double_valverun(
            (hum_current, 0),
            (ele_current, 0),
            &cloned,
            time - 1,
            highest,
            total + turnflow,
            turnflow + rate,
        ));
    }
    // Human closed and positive flow available? Run it!
    else if !hum_valve.open && hum_valve.rate > 0 {
        hum_valve.open = true;
        let rate = hum_valve.rate;
        let mut cloned = valves.clone();
        cloned.insert(hum_current, hum_valve);
        for &label in &ele_conns {
            if label == ele_last {
                continue;
            }
            curmax = curmax.max(double_valverun(
                (hum_current, 0),
                (label, ele_current),
                &cloned,
                time - 1,
                highest,
                total + turnflow,
                turnflow + rate,
            ));
        }
    }
    // Elephant closed and flow available? GOGOGOGOGO!
    else if !ele_valve.open && ele_valve.rate > 0 {
        ele_valve.open = true;
        let rate = ele_valve.rate;
        let mut cloned = valves.clone();
        cloned.insert(ele_current, ele_valve);
        for &label in &hum_conns {
            if label == hum_last {
                continue;
            }
            curmax = curmax.max(double_valverun(
                (label, hum_current),
                (ele_current, 0),
                &cloned,
                time - 1,
                highest,
                total + turnflow,
                turnflow + rate,
            ));
        }
    }
    // Neither has more flow available, time to walk all next paths instead
    else {
        for hum_label in hum_conns {
            if hum_label == hum_last {
                continue;
            }
            for &ele_label in &ele_conns {
                if ele_label == ele_last {
                    continue;
                }
                curmax = curmax.max(double_valverun(
                    (hum_label, hum_current),
                    (ele_label, ele_current),
                    valves,
                    time - 1,
                    highest,
                    total + turnflow,
                    turnflow,
                ));
            }
        }
    }
    curmax
}

#[inline]
pub fn part_one(parsed: &Valves) -> i64 {
    double_valverun((AA, 0), (AA, 0), parsed, 26, &mut HashMap::new(), 0, 0)
}

pub fn run(input: &str) -> i64 {
    part_one(&parse(input))
}
