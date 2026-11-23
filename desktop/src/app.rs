//! Native GUI app for Jiny Companion built with eframe/egui.

use crate::agentic_clipboard::{AgenticClipboard, ProcessedMessage};
use crate::llm::LlmClient;
use crate::watcher::ChatQuery;
use eframe::egui;
use std::sync::mpsc::{channel, Receiver, Sender};
use std::time::{Instant, SystemTime};

pub struct UiMessage {
    pub id: usize,
    pub source: String,
    pub question: String,
    pub answer: Option<String>,
    pub macro_title: Option<String>,
    pub macro_code: Option<String>,
    pub timestamp: String,
    pub is_pending: bool,
}

struct LlmTaskResponse {
    message_id: usize,
    result: Result<String, String>,
}

pub struct JinyDesktopApp {
    rx_chat: Receiver<ChatQuery>,
    tx_llm: Sender<LlmTaskResponse>,
    rx_llm: Receiver<LlmTaskResponse>,
    llm: LlmClient,
    clipboard: AgenticClipboard,
    messages: Vec<UiMessage>,
    next_id: usize,
    input_text: String,
    auto_copy_enabled: bool,
    always_on_top: bool,
    is_parchment_theme: bool,
    toast: Option<(String, Instant)>,
    is_thinking: bool,
}

impl JinyDesktopApp {
    pub fn new(rx_chat: Receiver<ChatQuery>) -> Self {
        println!("  [app] 1. Entrando en JinyDesktopApp::new...");
        let (tx_llm, rx_llm) = channel();
        println!("  [app] 2. Inicializando LlmClient...");
        let llm = LlmClient::new();
        println!("  [app] 3. Inicializando AgenticClipboard...");
        let clipboard = AgenticClipboard::new();
        println!("  [app] 4. Creando estructura JinyDesktopApp...");

        let app = Self {
            rx_chat,
            tx_llm,
            rx_llm,
            llm,
            clipboard,
            messages: Vec::new(),
            next_id: 1,
            input_text: String::new(),
            auto_copy_enabled: true,
            always_on_top: true,
            is_parchment_theme: false,
            toast: None,
            is_thinking: false,
        };
        println!("  [app] 5. JinyDesktopApp creada con éxito!");
        app
    }

    fn format_now() -> String {
        let dt = ChronoFallback::now();
        format!("{:02}:{:02}", dt.hour, dt.minute)
    }

    fn handle_question(&mut self, ctx: &egui::Context, source: &str, question: &str, locale: &str) {
        let q = question.trim().to_string();
        if q.is_empty() {
            return;
        }

        let id = self.next_id;
        self.next_id += 1;
        self.is_thinking = true;

        self.messages.push(UiMessage {
            id,
            source: source.to_string(),
            question: q.clone(),
            answer: None,
            macro_title: None,
            macro_code: None,
            timestamp: Self::format_now(),
            is_pending: true,
        });

        let tx = self.tx_llm.clone();
        let llm = self.llm.clone();
        let ctx_clone = ctx.clone();
        let q_clone = q;
        let loc = locale.to_string();

        // Non-blocking async worker thread for LLM / network query
        std::thread::spawn(move || {
            let result = llm.ask(&q_clone, &loc);
            let _ = tx.send(LlmTaskResponse {
                message_id: id,
                result,
            });
            ctx_clone.request_repaint();
        });
    }
}

impl eframe::App for JinyDesktopApp {
    fn update(&mut self, ctx: &egui::Context, _frame: &mut eframe::Frame) {
        static ONCE: std::sync::atomic::AtomicBool = std::sync::atomic::AtomicBool::new(false);
        if !ONCE.swap(true, std::sync::atomic::Ordering::Relaxed) {
            println!("  [app] >> 6. PRIMER FRAME RENDERIZADO EN PANTALLA! <<");
            ctx.send_viewport_cmd(egui::ViewportCommand::Visible(true));
            ctx.send_viewport_cmd(egui::ViewportCommand::Focus);
            ctx.send_viewport_cmd(egui::ViewportCommand::WindowLevel(egui::WindowLevel::AlwaysOnTop));
        }
        // Poll messages from background WoW chat watcher
        while let Ok(query) = self.rx_chat.try_recv() {
            self.handle_question(ctx, "WoW Chat (/jiny)", &query.question, &query.locale);
        }

        // Poll completed LLM responses from background worker threads
        while let Ok(resp) = self.rx_llm.try_recv() {
            let raw_answer = match resp.result {
                Ok(ans) => ans,
                Err(e) => format!("Error al consultar a Jiny: {e}"),
            };

            let processed: ProcessedMessage =
                self.clipboard.process_response(&raw_answer, self.auto_copy_enabled);

            if let Some(msg) = processed.toast_notification {
                self.toast = Some((msg, Instant::now()));
            }

            if let Some(msg) = self.messages.iter_mut().find(|m| m.id == resp.message_id) {
                msg.answer = Some(processed.display_text);
                msg.macro_title = processed.macro_title;
                msg.macro_code = processed.macro_code;
                msg.is_pending = false;
            }

            self.is_thinking = self.messages.iter().any(|m| m.is_pending);
        }

        // Apply theme colors
        let (bg_color, card_bg, text_color, gold_color, _accent_color) = if self.is_parchment_theme {
            (
                egui::Color32::from_rgb(229, 216, 184),
                egui::Color32::from_rgb(244, 236, 218),
                egui::Color32::from_rgb(45, 30, 18),
                egui::Color32::from_rgb(133, 77, 14),
                egui::Color32::from_rgb(113, 63, 18),
            )
        } else {
            // DarkGlass
            (
                egui::Color32::from_rgb(11, 14, 20),
                egui::Color32::from_rgb(18, 24, 38),
                egui::Color32::from_rgb(226, 232, 240),
                egui::Color32::from_rgb(255, 209, 0),
                egui::Color32::from_rgb(37, 99, 235),
            )
        };

        let mut style = (*ctx.style()).clone();
        style.visuals.panel_fill = bg_color;
        style.visuals.override_text_color = Some(text_color);
        ctx.set_style(style);

        // Topbar / Integrated Custom Title Bar
        egui::TopBottomPanel::top("topbar")
            .frame(
                egui::Frame::none()
                    .fill(card_bg)
                    .inner_margin(egui::Margin::symmetric(10.0, 8.0))
                    .stroke(egui::Stroke::new(1.0f32, egui::Color32::from_rgb(30, 41, 59))),
            )
            .show(ctx, |ui| {
                ui.horizontal(|ui| {
                    // Left area: Icon & Title & Status
                    let (rect, _) = ui.allocate_exact_size(egui::vec2(20.0, 20.0), egui::Sense::hover());
                    ui.painter().rect_filled(rect, 4.0, gold_color);
                    ui.painter().text(
                        rect.center(),
                        egui::Align2::CENTER_CENTER,
                        "J",
                        egui::FontId::monospace(12.0),
                        egui::Color32::BLACK,
                    );

                    ui.colored_label(gold_color, egui::RichText::new("JINY").strong().size(13.0));

                    if self.is_thinking {
                        ui.colored_label(
                            gold_color,
                            egui::RichText::new("🌀 Consultando...").size(11.0).italics(),
                        );
                    } else {
                        egui::Frame::none()
                            .fill(egui::Color32::from_rgb(6, 78, 59))
                            .rounding(10.0)
                            .inner_margin(egui::Margin::symmetric(6.0, 2.0))
                            .show(ui, |ui| {
                                ui.colored_label(
                                    egui::Color32::from_rgb(52, 211, 153),
                                    egui::RichText::new("● Classic 1.15.x").size(10.0),
                                );
                            });
                    }

                    // Right-side integrated window controls (Right to Left order)
                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                        // Close button [✕]
                        let close_btn = ui.button(
                            egui::RichText::new("✕")
                                .size(11.0)
                                .color(egui::Color32::from_rgb(239, 68, 68)),
                        );
                        if close_btn.clicked() {
                            ctx.send_viewport_cmd(egui::ViewportCommand::Close);
                        }

                        // Minimize button [—]
                        let min_btn = ui.button(egui::RichText::new("—").size(11.0));
                        if min_btn.clicked() {
                            ctx.send_viewport_cmd(egui::ViewportCommand::Minimized(true));
                        }

                        ui.separator();

                        // Pin (Always on top)
                        let pin_label = if self.always_on_top { "📌" } else { "📍" };
                        let pin_btn = ui.button(egui::RichText::new(pin_label).size(12.0));
                        if pin_btn.clicked() {
                            self.always_on_top = !self.always_on_top;
                            ctx.send_viewport_cmd(egui::ViewportCommand::WindowLevel(
                                if self.always_on_top {
                                    egui::WindowLevel::AlwaysOnTop
                                } else {
                                    egui::WindowLevel::Normal
                                },
                            ));
                        }

                        // Theme toggle
                        let theme_label = if self.is_parchment_theme { "📜" } else { "🌙" };
                        if ui.button(egui::RichText::new(theme_label).size(12.0)).clicked() {
                            self.is_parchment_theme = !self.is_parchment_theme;
                        }

                        // Auto-copy toggle
                        let copy_color = if self.auto_copy_enabled {
                            egui::Color32::from_rgb(52, 211, 153)
                        } else {
                            egui::Color32::GRAY
                        };
                        let copy_btn = ui.button(
                            egui::RichText::new("⚡ Auto-Copy")
                                .size(11.0)
                                .color(copy_color),
                        );
                        if copy_btn.clicked() {
                            self.auto_copy_enabled = !self.auto_copy_enabled;
                        }

                        // Draggable region: empty space between left badge and right buttons
                        let remaining_rect = ui.available_rect_before_wrap();
                        let drag_sense = ui.interact(remaining_rect, ui.id().with("title_drag"), egui::Sense::drag());
                        if drag_sense.dragged() {
                            ctx.send_viewport_cmd(egui::ViewportCommand::StartDrag);
                        }
                    });
                });
            });

        // Bottom input bar
        egui::TopBottomPanel::bottom("bottom_bar")
            .frame(
                egui::Frame::none()
                    .fill(card_bg)
                    .inner_margin(egui::Margin::symmetric(10.0, 8.0))
                    .stroke(egui::Stroke::new(1.0f32, egui::Color32::from_rgb(30, 41, 59))),
            )
            .show(ctx, |ui| {
            ui.add_space(8.0);
            ui.horizontal(|ui| {
                let text_edit = egui::TextEdit::singleline(&mut self.input_text)
                    .hint_text("Haz una pregunta o pide una macro...")
                    .desired_width(ui.available_width() - 80.0);
                let response = ui.add(text_edit);

                let submit = ui.button(egui::RichText::new("Enviar").strong()).clicked()
                    || (response.lost_focus() && ui.input(|i| i.key_pressed(egui::Key::Enter)));

                if submit && !self.input_text.trim().is_empty() {
                    let text = std::mem::take(&mut self.input_text);
                    self.handle_question(ctx, "Desktop", &text, "esES");
                }
            });
            ui.add_space(8.0);
        });

        // Toast notification banner
        if let Some((ref text, ref time)) = self.toast {
            if time.elapsed().as_secs() < 3 {
                egui::TopBottomPanel::top("toast_bar").show(ctx, |ui| {
                    egui::Frame::none()
                        .fill(egui::Color32::from_rgb(16, 185, 129))
                        .inner_margin(6.0)
                        .show(ui, |ui| {
                            ui.centered_and_justified(|ui| {
                                ui.colored_label(
                                    egui::Color32::BLACK,
                                    egui::RichText::new(text).strong().size(12.0),
                                );
                            });
                        });
                });
            } else {
                self.toast = None;
            }
        }

        // Central Chat Area
        egui::CentralPanel::default().show(ctx, |ui| {
            egui::ScrollArea::vertical().auto_shrink([false, false]).show(ui, |ui| {
                ui.add_space(8.0);

                if self.messages.is_empty() {
                    ui.vertical_centered(|ui| {
                        ui.add_space(80.0);
                        ui.colored_label(
                            gold_color,
                            egui::RichText::new("Jiny Companion • Classic Forever").strong().size(16.0),
                        );
                        ui.add_space(8.0);
                        ui.label("Escribe /jiny tu pregunta dentro de WoW o usa el campo de texto abajo.");
                        ui.label("Las respuestas y macros aparecen aquí al instante sin /reload.");
                    });
                }

                for msg in &self.messages {
                    // User bubble
                    ui.horizontal(|ui| {
                        ui.add_space(40.0);
                        egui::Frame::none()
                            .fill(card_bg)
                            .rounding(6.0)
                            .inner_margin(8.0)
                            .show(ui, |ui| {
                                ui.colored_label(
                                    egui::Color32::from_rgb(56, 189, 248),
                                    egui::RichText::new(format!("{} • {}", msg.source, msg.timestamp))
                                        .size(10.0)
                                        .strong(),
                                );
                                ui.label(&msg.question);
                            });
                    });
                    ui.add_space(6.0);

                    // Jiny bubble
                    egui::Frame::none()
                        .fill(card_bg)
                        .stroke(egui::Stroke::new(1.0f32, egui::Color32::from_rgb(30, 41, 59)))
                        .rounding(8.0)
                        .inner_margin(10.0)
                        .show(ui, |ui| {
                            ui.horizontal(|ui| {
                                ui.colored_label(
                                    gold_color,
                                    egui::RichText::new("Jiny (Asistente de Azeroth)").strong().size(12.0),
                                );
                                ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                                    ui.label(egui::RichText::new(&msg.timestamp).size(10.0).weak());
                                });
                            });

                            ui.add_space(4.0);

                            if msg.is_pending {
                                ui.horizontal(|ui| {
                                    ui.spinner();
                                    ui.colored_label(
                                        gold_color,
                                        egui::RichText::new("Consultando los archivos de Azeroth...")
                                            .italics()
                                            .size(12.0),
                                    );
                                });
                            } else if let Some(ref ans) = msg.answer {
                                ui.label(ans);

                                // Macro Card if present
                                if let Some(ref macro_code) = msg.macro_code {
                                    ui.add_space(8.0);
                                    egui::Frame::none()
                                        .fill(egui::Color32::from_rgb(10, 13, 20))
                                        .stroke(egui::Stroke::new(1.0f32, gold_color))
                                        .rounding(6.0)
                                        .inner_margin(8.0)
                                        .show(ui, |ui| {
                                            ui.horizontal(|ui| {
                                                let title = msg.macro_title.as_deref().unwrap_or("Macro Classic");
                                                ui.colored_label(gold_color, egui::RichText::new(title).strong().size(11.0));
                                                ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                                                    if ui.button(egui::RichText::new("📋 Copiar Macro").strong().size(11.0)).clicked() {
                                                        if self.clipboard.copy(macro_code) {
                                                            self.toast = Some((
                                                                "¡Macro copiada! Pulsa Ctrl + V en WoW".to_string(),
                                                                Instant::now(),
                                                            ));
                                                        }
                                                    }
                                                });
                                            });
                                            ui.add_space(4.0);
                                            ui.colored_label(
                                                egui::Color32::from_rgb(147, 197, 253),
                                                egui::RichText::new(macro_code).monospace().size(11.0),
                                            );
                                        });
                                }
                            }
                        });
                    ui.add_space(10.0);
                }
            });
        });

        // Request constant repaints if watcher thread might produce events or toast is active
        ctx.request_repaint_after(std::time::Duration::from_millis(200));
    }
}

struct ChronoFallback {
    hour: u32,
    minute: u32,
}

impl ChronoFallback {
    fn now() -> Self {
        let secs = SystemTime::now()
            .duration_since(SystemTime::UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs();
        let total_minutes = (secs / 60) % (24 * 60);
        Self {
            hour: (total_minutes / 60) as u32,
            minute: (total_minutes % 60) as u32,
        }
    }
}
