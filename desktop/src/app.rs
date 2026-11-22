//! Native GUI app for Jiny Companion built with eframe/egui.

use crate::agentic_clipboard::{AgenticClipboard, ProcessedMessage};
use crate::llm::LlmClient;
use crate::watcher::ChatQuery;
use eframe::egui;
use std::sync::mpsc::Receiver;
use std::time::{Instant, SystemTime};

pub struct UiMessage {
    pub source: String,
    pub question: String,
    pub answer: String,
    pub macro_title: Option<String>,
    pub macro_code: Option<String>,
    pub timestamp: String,
}

pub struct JinyDesktopApp {
    rx: Receiver<ChatQuery>,
    llm: LlmClient,
    clipboard: AgenticClipboard,
    messages: Vec<UiMessage>,
    input_text: String,
    auto_copy_enabled: bool,
    always_on_top: bool,
    is_parchment_theme: bool,
    toast: Option<(String, Instant)>,
    is_thinking: bool,
}

impl JinyDesktopApp {
    pub fn new(rx: Receiver<ChatQuery>) -> Self {
        let llm = LlmClient::new();
        let clipboard = AgenticClipboard::new();

        Self {
            rx,
            llm,
            clipboard,
            messages: Vec::new(),
            input_text: String::new(),
            auto_copy_enabled: true,
            always_on_top: true,
            is_parchment_theme: false,
            toast: None,
            is_thinking: false,
        }
    }

    fn format_now() -> String {
        let dt = ChronoFallback::now();
        format!("{:02}:{:02}", dt.hour, dt.minute)
    }

    fn handle_question(&mut self, source: &str, question: &str, locale: &str) {
        let q = question.trim().to_string();
        if q.is_empty() {
            return;
        }

        self.is_thinking = true;
        let answer_res = self.llm.ask(&q, locale);
        self.is_thinking = false;

        let raw_answer = match answer_res {
            Ok(ans) => ans,
            Err(e) => format!("Error al consultar a Jiny: {e}"),
        };

        let processed: ProcessedMessage =
            self.clipboard.process_response(&raw_answer, self.auto_copy_enabled);

        if let Some(msg) = processed.toast_notification {
            self.toast = Some((msg, Instant::now()));
        }

        self.messages.push(UiMessage {
            source: source.to_string(),
            question: q,
            answer: processed.display_text,
            macro_title: processed.macro_title,
            macro_code: processed.macro_code,
            timestamp: Self::format_now(),
        });
    }
}

impl eframe::App for JinyDesktopApp {
    fn update(&mut self, ctx: &egui::Context, _frame: &mut eframe::Frame) {
        // Poll messages from background WoW chat watcher
        while let Ok(query) = self.rx.try_recv() {
            self.handle_question("WoW Chat (/jiny)", &query.question, &query.locale);
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

        // Topbar
        egui::TopBottomPanel::top("topbar").show(ctx, |ui| {
            ui.add_space(6.0);
            ui.horizontal(|ui| {
                // Gold Icon
                let (rect, _) = ui.allocate_exact_size(egui::vec2(22.0, 22.0), egui::Sense::hover());
                ui.painter().rect_filled(rect, 4.0, gold_color);
                ui.painter().text(
                    rect.center(),
                    egui::Align2::CENTER_CENTER,
                    "J",
                    egui::FontId::monospace(13.0),
                    egui::Color32::BLACK,
                );

                ui.colored_label(gold_color, egui::RichText::new("JINY").strong().size(13.0));

                // Status pill
                if self.is_thinking {
                    ui.colored_label(
                        egui::Color32::from_rgb(56, 189, 248),
                        egui::RichText::new("● Pensando...").size(11.0),
                    );
                } else {
                    ui.colored_label(
                        egui::Color32::from_rgb(16, 185, 129),
                        egui::RichText::new("● EN VIVO (Classic)").size(11.0),
                    );
                }

                ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                    // Theme toggle
                    let theme_label = if self.is_parchment_theme { "Tema: Pergamino" } else { "Tema: DarkGlass" };
                    if ui.button(theme_label).clicked() {
                        self.is_parchment_theme = !self.is_parchment_theme;
                    }

                    // Always on Top (Pin)
                    let pin_text = if self.always_on_top { "📌 Fijado" } else { "📌 Desfijado" };
                    if ui.selectable_label(self.always_on_top, pin_text).clicked() {
                        self.always_on_top = !self.always_on_top;
                        let level = if self.always_on_top {
                            egui::WindowLevel::AlwaysOnTop
                        } else {
                            egui::WindowLevel::Normal
                        };
                        ctx.send_viewport_cmd(egui::ViewportCommand::WindowLevel(level));
                        self.toast = Some((
                            if self.always_on_top {
                                "📌 Ventana fijada siempre visible sobre WoW".to_string()
                            } else {
                                "📌 Modo ventana normal".to_string()
                            },
                            Instant::now(),
                        ));
                    }

                    // Auto-copy toggle
                    let copy_label = if self.auto_copy_enabled { "📋 Auto-Copy: ON" } else { "📋 Auto-Copy: OFF" };
                    if ui.selectable_label(self.auto_copy_enabled, copy_label).clicked() {
                        self.auto_copy_enabled = !self.auto_copy_enabled;
                        self.toast = Some((
                            if self.auto_copy_enabled {
                                "📋 Auto-Copy activado (Macros listas para Ctrl+V en WoW)".to_string()
                            } else {
                                "📋 Auto-Copy desactivado".to_string()
                            },
                            Instant::now(),
                        ));
                    }
                });
            });
            ui.add_space(6.0);
        });

        // Bottom Input bar
        egui::TopBottomPanel::bottom("bottom_bar").show(ctx, |ui| {
            ui.add_space(6.0);
            ui.horizontal(|ui| {
                let text_edit = egui::TextEdit::singleline(&mut self.input_text)
                    .hint_text("Pregunta a Jiny o escribe /jiny en el chat de WoW...")
                    .desired_width(ui.available_width() - 80.0);

                let response = ui.add(text_edit);
                let enter_pressed = response.lost_focus() && ctx.input(|i| i.key_pressed(egui::Key::Enter));

                if (ui.button(egui::RichText::new("Enviar").strong()).clicked() || enter_pressed)
                    && !self.input_text.trim().is_empty()
                {
                    let q = std::mem::take(&mut self.input_text);
                    self.handle_question("Tú (Desktop)", &q, "esES");
                    response.request_focus();
                }
            });
            ui.add_space(6.0);
        });

        // Toast popup bar (if active < 2.5s)
        if let Some((ref msg, time)) = self.toast {
            if time.elapsed().as_secs_f32() < 2.5 {
                egui::TopBottomPanel::top("toast_panel").show(ctx, |ui| {
                    ui.add_space(2.0);
                    ui.centered_and_justified(|ui| {
                        ui.colored_label(
                            egui::Color32::from_rgb(56, 189, 248),
                            egui::RichText::new(msg).strong().size(12.0),
                        );
                    });
                    ui.add_space(2.0);
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
                            ui.label(&msg.answer);

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
