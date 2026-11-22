//! Agentic clipboard processor: detects macros & commands and handles clipboard auto-copy.

use arboard::Clipboard;
use regex::Regex;
use std::sync::Mutex;

lazy_static_init!();

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ProcessedMessage {
    pub has_macro: bool,
    pub macro_title: Option<String>,
    pub macro_code: Option<String>,
    pub display_text: String,
    pub toast_notification: Option<String>,
}

pub struct AgenticClipboard {
    clipboard: Option<Mutex<Clipboard>>,
}

impl AgenticClipboard {
    pub fn new() -> Self {
        let clipboard = match Clipboard::new() {
            Ok(cb) => Some(Mutex::new(cb)),
            Err(e) => {
                eprintln!("[Jiny AgenticClipboard] Warning: Could not access OS clipboard: {e}");
                None
            }
        };
        Self { clipboard }
    }

    /// Safely copy Unicode string into OS clipboard
    pub fn copy(&self, text: &str) -> bool {
        if let Some(cb_mutex) = &self.clipboard {
            if let Ok(mut cb) = cb_mutex.lock() {
                if cb.set_text(text.to_string()).is_ok() {
                    return true;
                }
            }
        }

        // Windows fallback via PowerShell if arboard fails
        #[cfg(target_os = "windows")]
        {
            use std::process::Command;
            let mut cmd = Command::new("powershell");
            cmd.args(["-NoProfile", "-NonInteractive", "-Command", "Set-Clipboard -Value $env:JINY_CLIP_TEXT"]);
            cmd.env("JINY_CLIP_TEXT", text);
            if let Ok(status) = cmd.status() {
                return status.success();
            }
        }

        false
    }

    /// Parse assistant response, detect macros, format text and optionally auto-copy.
    pub fn process_response(&self, text: &str, auto_copy: bool) -> ProcessedMessage {
        let macro_regex = Regex::new(r#"(?s)\[JINY_MACRO(?:\s+name="([^"]*)")?[^\]]*\](.*?)\[/JINY_MACRO\]"#)
            .expect("Valid macro regex");
        let code_block_regex = Regex::new(r"(?s)```[a-zA-Z0-9_-]*\s*(.*?)```")
            .expect("Valid code block regex");

        let mut macro_title = None;
        let mut macro_code = None;

        if let Some(captures) = macro_regex.captures(text) {
            macro_title = captures.get(1).map(|m| m.as_str().trim().to_string());
            let code = captures.get(2).map_or("", |m| m.as_str()).trim().to_string();
            if !code.is_empty() {
                macro_code = Some(code);
            }
        } else if let Some(captures) = code_block_regex.captures(text) {
            let code = captures.get(1).map_or("", |m| m.as_str()).trim().to_string();
            // Check if code contains WoW macro commands
            if code.lines().any(|l| {
                let l = l.trim_start();
                l.starts_with("#showtooltip")
                    || l.starts_with("/cast")
                    || l.starts_with("/use")
                    || l.starts_with("/target")
                    || l.starts_with("/cancelaura")
                    || l.starts_with("/petattack")
                    || l.starts_with("/equip")
            }) {
                macro_title = Some("Macro Classic".to_string());
                macro_code = Some(code);
            }
        }

        let has_macro = macro_code.is_some();
        let mut toast_notification = None;

        if auto_copy {
            if let Some(ref code) = macro_code {
                if self.copy(code) {
                    toast_notification = Some("📋 ¡Macro copiada! Pulsa Ctrl + V en WoW".to_string());
                }
            }
        }

        // Clean WoW specific color and hyperlink codes for readable display
        let color_re = Regex::new(r"\|c[0-9a-fA-F]{8}").unwrap();
        let cleaned = color_re.replace_all(text, "");
        let cleaned = cleaned.replace("|r", "");
        let link_re = Regex::new(r"\|H[^|]*\|h([^|]*)\|h").unwrap();
        let cleaned = link_re.replace_all(&cleaned, "$1");

        ProcessedMessage {
            has_macro,
            macro_title,
            macro_code,
            display_text: cleaned.to_string(),
            toast_notification,
        }
    }
}

// Simple macro helper to avoid external lazy_static dependency
macro_rules! lazy_static_init {
    () => {};
}
use lazy_static_init;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_process_jiny_macro_tag() {
        let clipboard = AgenticClipboard::new();
        let input = "Aquí tienes tu macro:\n[JINY_MACRO name=\"Aspectos Cazador\"]\n#showtooltip\n/cast !Aspecto del guepardo\n[/JINY_MACRO]\n¡Disfrútala!";
        let processed = clipboard.process_response(input, false);

        assert!(processed.has_macro);
        assert_eq!(processed.macro_title.as_deref(), Some("Aspectos Cazador"));
        assert!(processed.macro_code.unwrap().contains("/cast !Aspecto del guepardo"));
    }

    #[test]
    fn test_process_code_block_macro() {
        let clipboard = AgenticClipboard::new();
        let input = "Prueba esta macro en WoW Classic:\n```lua\n#showtooltip Golpe mortal\n/cast Golpe mortal\n/startattack\n```";
        let processed = clipboard.process_response(input, false);

        assert!(processed.has_macro);
        assert_eq!(processed.macro_title.as_deref(), Some("Macro Classic"));
        assert!(processed.macro_code.unwrap().contains("/startattack"));
    }

    #[test]
    fn test_strip_wow_color_and_hyperlinks() {
        let clipboard = AgenticClipboard::new();
        let input = "Obtén |cffff8000|Hitem:19019:0:0:0|h[Trueno Furioso]|h|r en Silithus.";
        let processed = clipboard.process_response(input, false);

        assert_eq!(processed.display_text, "Obtén [Trueno Furioso] en Silithus.");
    }
}
