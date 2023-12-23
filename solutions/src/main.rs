use std::env;
use std::process;

#[derive(Clone, Debug)]
struct Solution {
    key:     String, // TEXT
    day:     u8,     // INTEGER
    part:    u8,     // INTEGER
    answer:  u64,    // INTEGER
    answer2: u64,    // ?
}

fn solutions(conn: &rusqlite::Connection, day: u8, part: u8) {
    // Fetch the list of solutions for the requested day and part.
    let mut stmt = conn
        .prepare("SELECT key, day, part, answer, answer2 FROM solutions WHERE day = ?1 AND part = ?2")
        .unwrap();
    let solutions = stmt
        .query_map(&[&day, &part], |row| {
            Ok(Solution {
                key: row.get(0).unwrap(),
                day: row.get(1).unwrap(),
                part: row.get(2).unwrap(),
                answer: row.get(3).unwrap(),
                answer2: row.get(4).unwrap(),
            })
        })
        .unwrap()
        .map(|r| r.unwrap())
        .collect::<Vec<_>>();
    // Print the solutions.
    for solution in &solutions {
        let Solution { key, day, part, answer, answer2 } = solution;
        println!("{key}, {day}, {part}, {answer}, {answer2}");
    }
    // Verify that there are either no solutions or solutions for each of the 3 inputs.
    assert!(solutions.is_empty() || solutions.len() == 3);
}

#[derive(Clone, Debug)]
struct Answer {
//    user:    String, // TEXT
//    code:    String, // BLOB
    day:     u8,     // INTEGER
    part:    u8,     // INTEGER
//    time:    f64,    // REAL
    answer:  u64,    // INTEGER
//    answer2: u64,    // TEXT
    count:   u64,    // INTEGER
}

fn runs(conn: &rusqlite::Connection, day: u8, part: u8) {
    // Find all the runs for the requested day and part.
    let mut stmt = conn
        .prepare("SELECT day, part, answer, COUNT(answer) FROM runs WHERE day = ?1 AND part = ?2 GROUP BY answer ORDER BY COUNT(answer) DESC")
        .unwrap();
    let answers = stmt
        .query_map(&[&day, &part], |row| {
            Ok(
                Answer {
                    day: row.get(0).unwrap(),
                    part: row.get(1).unwrap(),
                    answer: row.get(2).unwrap(),
                    count: row.get(3).unwrap(),
                }
            )
        })
        .unwrap()
        .map(|r| r.unwrap())
        .collect::<Vec<_>>();
    // Print the answers.
    for answer in &answers {
        let Answer { day, part, answer, count } = answer;
        println!("{day}, {part}, {answer}, {count}");
    }
}

#[derive(Clone, Copy, Debug)]
enum Command {
    Solutions,
    Runs,
}

fn run(cmd: Command, day: u8, part: u8) {
    // Connect to the database.
    let conn = rusqlite::Connection::open("database.db").unwrap();
    match cmd {
        Command::Solutions => solutions(&conn, day, part),
        Command::Runs => runs(&conn, day, part),
    }
}

fn main() {
    // Parse the day and part from the command line.
    let (cmd, day, part) = {
        let args = env::args().collect::<Vec<_>>();
        match (
            args.get(0),
            args.get(1).map(|s| s.as_str()),
            args.get(2).map(|v| v.parse::<u8>()),
            args.get(3).map(|v| v.parse::<u8>()),
        ) {
            (Some(_), Some("solutions"), Some(Ok(day)), Some(Ok(part))) => (Command::Solutions, day, part),
            (Some(_), Some("runs"), Some(Ok(day)), Some(Ok(part))) => (Command::Runs, day, part),
            (program, _, _, _) => {
                eprintln!("Usage: {} <solutions|runs> <day> <part>", program.map(|s| s.as_str()).unwrap_or("solutions"));
                process::exit(1);
            },
        }
    };
    assert!(day >= 1u8 && day <= 25);
    assert!(part >= 1 && part <= 2);
    run(cmd, day, part)
}
