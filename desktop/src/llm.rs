//! LLM client connecting to Gemini 3.8 Flash with offline Classic Era preview fallback.

use serde::{Deserialize, Serialize};
use std::path::Path;

#[derive(Clone)]
pub struct LlmClient {
    api_key: String,
    model: String,
}

#[derive(Serialize)]
struct GeminiPart {
    text: String,
}

#[derive(Serialize)]
struct GeminiContent {
    #[serde(skip_serializing_if = "Option::is_none")]
    role: Option<String>,
    parts: Vec<GeminiPart>,
}

#[derive(Serialize)]
struct GeminiRequest {
    system_instruction: GeminiContent,
    contents: Vec<GeminiContent>,
}

#[derive(Deserialize)]
struct GeminiCandidatePart {
    text: Option<String>,
}

#[derive(Deserialize)]
struct GeminiCandidateContent {
    parts: Option<Vec<GeminiCandidatePart>>,
}

#[derive(Deserialize)]
struct GeminiCandidate {
    content: Option<GeminiCandidateContent>,
}

#[derive(Deserialize)]
struct GeminiResponse {
    candidates: Option<Vec<GeminiCandidate>>,
}

impl LlmClient {
    pub fn new() -> Self {
        let env_key = std::env::var("GEMINI_API_KEY").unwrap_or_default().trim().to_string();
        let api_key = if !env_key.is_empty() {
            env_key
        } else {
            Self::read_key_from_config()
        };

        let model = std::env::var("GEMINI_MODEL")
            .unwrap_or_else(|_| "gemini-2.5-flash".to_string());

        Self {
            api_key,
            model,
        }
    }

    fn read_key_from_config() -> String {
        let candidates = [
            Path::new("companion/config.json"),
            Path::new("../companion/config.json"),
            Path::new("jiny/companion/config.json"),
        ];

        for path in candidates {
            if path.exists() {
                if let Ok(raw) = std::fs::read_to_string(path) {
                    if let Ok(val) = serde_json::from_str::<serde_json::Value>(&raw) {
                        if let Some(k) = val.get("api_key").and_then(|v| v.as_str()) {
                            let trimmed = k.trim().to_string();
                            if !trimmed.is_empty() {
                                return trimmed;
                            }
                        }
                    }
                }
            }
        }

        String::new()
    }

    #[allow(dead_code)]
    pub fn has_api_key(&self) -> bool {
        !self.api_key.is_empty()
    }

    pub fn ask(&self, question: &str, locale: &str, history: &[(String, String)]) -> Result<String, String> {
        let _q_lower = question.to_lowercase();

        // If no API key or asked for preview/macro offline, generate instant Classic Forever response
        if self.api_key.is_empty() {
            return Ok(Self::generate_offline_preview(question, locale));
        }

        let url = format!(
            "https://generativelanguage.googleapis.com/v1beta/models/{}:generateContent?key={}",
            self.model, self.api_key
        );

        let system_text = format!(
            "Eres Jiny, la compañera e inteligencia artificial para World of Warcraft Classic Forever \
            (versión 1.15.x / Classic Era / Vanilla, nivel máximo 60, Kalimdor y Reinos del Este exclusivamente). \
            Responde en el idioma del usuario ({locale}). Sé concisa, inmersiva, precisa y útil (2 a 5 oraciones claras).\n\n\
            REGLAS ESTRICTAS DE CONOCIMIENTO (ANTI-ALUCINACIÓN):\n\
            1. ÁMBITO Y TEMPORALIDAD: Tu conocimiento está anclado en WoW Classic Era 1.15.x (Vanilla puro). \
            NUNCA asumas mecánicas modernas ni inventes datos. El nivel máximo es 60, no hay monturas voladoras ni talentos de expansiones posteriores.\n\
            2. CAZADORES Y MASCOTAS EN CLASSIC ERA: En Vanilla/Classic Era 1.15.x NO existen especializaciones de mascotas (Ferocidad, Tenacidad, Astucia) \
            ni árboles de talentos para mascotas. Las mascotas aprenden habilidades básicas (Mordisco, Zarpazo, Bramido, etc.) adiestrando bestias salvajes en el mundo.\n\
            3. DISTINCIÓN DE EXPANSIONES Y SEASON OF DISCOVERY:\n\
               - Si el usuario te pregunta por habilidades añadidas en expansiones posteriores como Wrath of the Lich King (ejemplo: 'Savage Rend' / 'Desgarro Salvaje' en raptors, añadida en WotLK) \
                 o por contenido/runas de Season of Discovery (como el 'Cozy Sleeping Bag' / 'Saco de dormir acogedor' o tiendas de acampar que otorgan bonificación de descanso acumulable):\n\
                 ACLARÁSELO CON TOTAL TRANSPARENCIA. Explica de dónde proviene exactamente la habilidad u objeto (ej: 'Esa habilidad/objeto proviene de WotLK/Season of Discovery...'), \
                 detalla su funcionamiento real y aclara cuál es la realidad en Classic Era 1.15.x pura.\n\
               - NUNCA inventes PNJs ficticios, coordenadas inventadas (como 'Young Stranglethorn Raptors en nivel 10') ni le atribuyas habilidades de mascotas a otras clases (como decir que Savage Rend es de Guerrero).\n\
            4. PRECISIÓN Y COORDENADAS: Escribe las coordenadas siempre en formato (XX.X, YY.Y). Si no estás 100% segura de una coordenada o dato, admítelo claramente en lugar de adivinar.\n\
            5. MACROS: Si el usuario te pide una macro, envuélvela SIEMPRE en etiquetas [JINY_MACRO name=\"Título de la macro\"]...[/JINY_MACRO] con comandos de WoW Classic válidos (#showtooltip, /cast, etc.)."
        );

        let mut contents = Vec::new();

        // Include recent multi-turn conversation history
        for (hist_q, hist_a) in history {
            let hq = hist_q.trim();
            let ha = hist_a.trim();
            if !hq.is_empty() && !ha.is_empty() {
                contents.push(GeminiContent {
                    role: Some("user".to_string()),
                    parts: vec![GeminiPart { text: hq.to_string() }],
                });
                contents.push(GeminiContent {
                    role: Some("model".to_string()),
                    parts: vec![GeminiPart { text: ha.to_string() }],
                });
            }
        }

        // Current user turn
        contents.push(GeminiContent {
            role: Some("user".to_string()),
            parts: vec![GeminiPart { text: question.to_string() }],
        });

        let req_body = GeminiRequest {
            system_instruction: GeminiContent {
                role: None,
                parts: vec![GeminiPart { text: system_text }],
            },
            contents,
        };

        let client = reqwest::blocking::Client::builder()
            .timeout(std::time::Duration::from_secs(60))
            .build()
            .map_err(|e| format!("HTTP client build error: {e}"))?;

        let resp = client
            .post(&url)
            .json(&req_body)
            .send()
            .map_err(|e| {
                let err_str = e.to_string();
                if let Some(pos) = err_str.find("key=") {
                    format!("Error de red o timeout al consultar a Gemini: {}", &err_str[..pos])
                } else {
                    format!("Error de red al consultar a Gemini: {err_str}")
                }
            })?;

        if !resp.status().is_success() {
            let status = resp.status();
            let err_txt = resp.text().unwrap_or_default();
            return Err(format!("Gemini API error ({status}): {err_txt}"));
        }

        let gemini_resp: GeminiResponse = resp
            .json()
            .map_err(|e| format!("JSON parse error: {e}"))?;

        if let Some(candidates) = gemini_resp.candidates {
            if let Some(first) = candidates.into_iter().next() {
                if let Some(content) = first.content {
                    if let Some(parts) = content.parts {
                        let full_text: String = parts
                            .into_iter()
                            .filter_map(|p| p.text)
                            .collect::<Vec<_>>()
                            .join("");
                        if !full_text.is_empty() {
                            return Ok(full_text);
                        }
                    }
                }
            }
        }

        Ok(Self::generate_offline_preview(question, locale))
    }

    fn generate_offline_preview(question: &str, locale: &str) -> String {
        let q = question.to_lowercase();

        if q.contains("macro") {
            if q.contains("cazador") || q.contains("hunter") || q.contains("guepardo") || q.contains("aspecto") {
                return "¡Por supuesto camarada cazador! Aquí tienes la macro solicitada para alternar aspectos con modificador Alt:\n\n[JINY_MACRO name=\"Macro de Cazador: Aspectos\"]\n#showtooltip\n/cast [mod:alt] Aspecto del guepardo; Aspecto del halcón\n[/JINY_MACRO]\n\n¡La macro ha sido copiada automáticamente a tu portapapeles!".to_string();
            }
            return "Aquí tienes una macro clásica de WoW Classic optimizada:\n\n[JINY_MACRO name=\"Macro Classic\"]\n#showtooltip\n/cast [combat] Fuego interno; Palabra de poder: entereza\n[/JINY_MACRO]\n\nCopiada al portapapeles, pulsa Ctrl + V en WoW.".to_string();
        }

        if q.contains("mankrik") {
            return "Mankrik se encuentra en **El Cruce** (*The Crossroads*), en Los Baldíos, en las coordenadas (52.1, 31.6).\n\nEs quien te otorga la misión «Perdidos en el combate». Si buscas el cuerpo de su esposa, yace más al sur en las coordenadas (49.3, 50.4).".to_string();
        }

        if q.contains("colmillo") || q.contains("shadowfang") {
            return "El **Castillo de Colmillo Oscuro** (*Shadowfang Keep*) se encuentra en el **Bosque de Argénteos** (*Silverpine Forest*), al sur de Aldea Piroleña. Es una mazmorra recomendada para niveles 22 a 30.".to_string();
        }

        format!(
            "Jiny Classic Forever ({locale}): He recibido tu consulta: «{question}». Todo en orden en Azeroth. Prueba a pedirme una macro escribiendo «macro de cazador» o una ubicación como «dónde está Mankrik»."
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_offline_preview_generation() {
        let client = LlmClient {
            api_key: String::new(),
            model: "gemini-2.5-flash".to_string(),
        };
        let ans = client.ask("donde esta mankrik?", "esES", &[]).unwrap();
        assert!(ans.contains("El Cruce"));
        assert!(ans.contains("52.1, 31.6"));
    }

    #[test]
    fn test_offline_macro_generation() {
        let client = LlmClient {
            api_key: String::new(),
            model: "gemini-2.5-flash".to_string(),
        };
        let ans = client.ask("macro cazador", "esES", &[]).unwrap();
        assert!(ans.contains("[JINY_MACRO"));
        assert!(ans.contains("Aspecto"));
    }
}
