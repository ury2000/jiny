//! Incremental byte-offset watcher for WoWChatLog.txt with strict privacy filtering.

use regex::Regex;
use std::collections::HashSet;
use std::fs::File;
use std::io::{Read, Seek, SeekFrom};
use std::path::{Path, PathBuf};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ChatQuery {
    pub req_id: String,
    pub locale: String,
    pub question: String,
}

pub struct ChatLogWatcher {
    log_path: PathBuf,
    offset: u64,
    remainder: String,
    seen_ids: HashSet<String>,
    query_regex: Regex,
}

impl ChatLogWatcher {
    pub fn new(log_path: impl Into<PathBuf>, start_at_end: bool) -> Self {
        let path = log_path.into();
        let mut initial_offset = 0u64;

        if start_at_end && path.exists() {
            if let Ok(meta) = std::fs::metadata(&path) {
                // Start directly at current EOF so only fresh queries are captured
                initial_offset = meta.len();
            }
        }

        let query_regex = Regex::new(r"\[JINY_Q#([A-Za-z0-9_-]+)#([A-Za-z]+)\]\s+(.+?)\s*$")
            .expect("Valid query regex");

        Self {
            log_path: path,
            offset: initial_offset,
            remainder: String::new(),
            seen_ids: HashSet::new(),
            query_regex,
        }
    }

    pub fn poll(&mut self) -> Vec<ChatQuery> {
        if !self.log_path.exists() {
            return Vec::new();
        }

        let meta = match std::fs::metadata(&self.log_path) {
            Ok(m) => m,
            Err(_) => return Vec::new(),
        };

        let file_len = meta.len();
        if file_len < self.offset {
            // File was truncated or rotated
            self.offset = 0;
            self.remainder.clear();
        }

        if file_len == self.offset {
            return Vec::new();
        }

        let mut file = match File::open(&self.log_path) {
            Ok(f) => f,
            Err(_) => return Vec::new(),
        };

        if file.seek(SeekFrom::Start(self.offset)).is_err() {
            return Vec::new();
        }

        let mut buffer = Vec::new();
        let bytes_read = match file.read_to_end(&mut buffer) {
            Ok(n) => n,
            Err(_) => return Vec::new(),
        };

        self.offset += bytes_read as u64;

        let incoming_text = String::from_utf8_lossy(&buffer);
        let mut full_text = std::mem::take(&mut self.remainder);
        full_text.push_str(&incoming_text);

        let mut lines: Vec<&str> = full_text.split('\n').collect();

        // If the text didn't end with a newline, the last segment is incomplete
        if !full_text.ends_with('\n') && !lines.is_empty() {
            self.remainder = lines.pop().unwrap_or("").to_string();
        }

        let mut queries = Vec::new();
        for raw_line in lines {
            let line = raw_line.trim_end_matches('\r').trim();
            if let Some(captures) = self.query_regex.captures(line) {
                let req_id = captures.get(1).map_or("", |m| m.as_str()).to_string();
                let locale = captures.get(2).map_or("", |m| m.as_str()).to_string();
                let question = captures.get(3).map_or("", |m| m.as_str()).trim().to_string();

                if !question.is_empty() && self.seen_ids.insert(req_id.clone()) {
                    queries.push(ChatQuery {
                        req_id,
                        locale,
                        question,
                    });
                }
            }
        }

        queries
    }

    #[allow(dead_code)]
    pub fn log_path(&self) -> &Path {
        &self.log_path
    }

    #[allow(dead_code)]
    pub fn current_offset(&self) -> u64 {
        self.offset
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;

    #[test]
    fn test_parse_jiny_query() {
        let temp_dir = std::env::temp_dir();
        let log_file = temp_dir.join(format!("test_wow_chat_{}.txt", std::time::SystemTime::now().elapsed().unwrap_or_default().as_nanos()));

        {
            let mut f = File::create(&log_file).expect("create test log file");
            writeln!(f, "11/22 18:00:00.000  To [Azok]: [JINY_Q#req-999#esES] ¿Dónde está Mankrik?").unwrap();
        }

        let mut watcher = ChatLogWatcher::new(&log_file, true);
        let mut f = std::fs::OpenOptions::new().append(true).open(&log_file).unwrap();
        writeln!(f, "11/22 18:00:01.000  To [Azok]: [JINY_Q#req-1000#esES] ¿Dónde está Mankrik?").unwrap();
        drop(f);

        let queries = watcher.poll();
        assert!(!queries.is_empty());
        assert!(queries.iter().any(|q| q.req_id == "req-1000" && q.question == "¿Dónde está Mankrik?"));

        let _ = std::fs::remove_file(&log_file);
    }
}
