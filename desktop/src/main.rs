mod agentic_clipboard;
mod app;
mod llm;
mod watcher;

use app::JinyDesktopApp;
use eframe::egui;
use std::path::PathBuf;
use std::sync::mpsc;
use std::thread;
use std::time::Duration;
use watcher::ChatLogWatcher;

fn resolve_wow_chatlog_path() -> PathBuf {
    let candidates = [
        PathBuf::from(r"D:\Games\Bnet\World of Warcraft\_forever_\Logs\WoWChatLog.txt"),
        PathBuf::from("_forever_/Logs/WoWChatLog.txt"),
        PathBuf::from("../_forever_/Logs/WoWChatLog.txt"),
        PathBuf::from("Logs/WoWChatLog.txt"),
    ];

    for candidate in candidates {
        if candidate.exists() {
            return candidate;
        }
    }

    // Default fallback path for WoW Classic Forever
    PathBuf::from(r"D:\Games\Bnet\World of Warcraft\_forever_\Logs\WoWChatLog.txt")
}

fn main() -> eframe::Result<()> {
    let log_path = resolve_wow_chatlog_path();
    println!("Jiny Desktop Companion (Rust Nativo 1.15.x)");
    println!("  Chat Log Path: {}", log_path.display());
    println!("  Agentic Clipboard: ACTIVO");
    println!("  Iniciando ventana lateral...");
    println!("  Llamando a eframe::run_native...");

    let (tx, rx) = mpsc::channel();

    // Spawn background file watcher thread for WoWChatLog.txt
    let watcher_path = log_path.clone();
    thread::spawn(move || {
        let mut watcher = ChatLogWatcher::new(watcher_path, true);
        loop {
            let queries = watcher.poll();
            for q in queries {
                println!("[WoW Log] #{}: {}", q.req_id, q.question);
                if tx.send(q).is_err() {
                    break;
                }
            }
            thread::sleep(Duration::from_millis(250));
        }
    });

    let native_options = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default()
            .with_title("Jiny Desktop Companion • Classic Forever")
            .with_inner_size([480.0, 680.0])
            .with_min_inner_size([360.0, 420.0])
            .with_position([100.0, 100.0])
            .with_visible(true)
            .with_active(true)
            .with_always_on_top(),
        ..Default::default()
    };

    eframe::run_native(
        "Jiny Desktop Companion",
        native_options,
        Box::new(|_cc| {
            println!("  [eframe] >> Setup closure ejecutándose <<");
            Ok(Box::new(JinyDesktopApp::new(rx)))
        }),
    )
}
