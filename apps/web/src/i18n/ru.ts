/**
 * Single UI string dictionary, RU only for now (spec 03 §7).
 *
 * Every user-visible text lives here: literals scattered in components are
 * a review defect. Keys are `screen.element` in kebab-case; EN columns
 * arrive with E5a (Locale widens without refactoring callers).
 */

export type Locale = "ru";

const RU = {
  "app.name": "Pomotivato",
  "nav.tasks": "Задачи",
  "nav.focus": "Фокус",
  "nav.settings": "Настройки",

  "app.placeholder.title": "Раздел в работе",
  "app.placeholder.body":
    "Экран появится в ближайших PR этапа MVP. Каркас, навигация и словарь — уже живые.",

  "error.network": "Сервер не отвечает. Проверь, что Pomotivato запущен.",
  "error.unknown": "Что-то пошло не так. Попробуй ещё раз.",
} as const;

export type MessageKey = keyof typeof RU;

const DICTIONARIES: Record<Locale, Record<MessageKey, string>> = { ru: RU };

export function t(key: MessageKey, locale: Locale = "ru"): string {
  return DICTIONARIES[locale][key];
}
