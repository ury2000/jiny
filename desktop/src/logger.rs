use std::fs::OpenOptions;
use std::io::Write;
use std::sync::Mutex;
use std::time::SystemTime;

static LOG_MUTEX: Mutex<()> = Mutex::new(());

pub fn log(level: &str, msg: impl AsRef<str>) {
    let now = SystemTime::now()
        .duration_since(SystemTime::UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs();
    let total_mins = (now / 60) % (24 * 60);
    let h = total_mins / 60;
    let m = total_mins % 60;
    let s = now % 60;
    let line = format!("[{:02}:{:02}:{:02}] [{}] {}\n", h, m, s, level, msg.as_ref());

    print!("{}", line);

    if let Ok(_lock) = LOG_MUTEX.lock() {
        let targets = [
            r"D:\Games\Bnet\World of Warcraft\jiny\desktop\jiny_desktop.log",
            "jiny_desktop.log",
        ];
        for target in targets {
            if let Ok(mut f) = OpenOptions::new().create(true).append(true).open(target) {
                let _ = f.write_all(line.as_bytes());
                let _ = f.flush();
                break;
            }
        }
    }
}

pub fn info(msg: impl AsRef<str>) {
    log("INFO", msg);
}

pub fn warn(msg: impl AsRef<str>) {
    log("WARN", msg);
}

pub fn error(msg: impl AsRef<str>) {
    log("ERROR", msg);
}

pub fn debug(msg: impl AsRef<str>) {
    log("DEBUG", msg);
}
