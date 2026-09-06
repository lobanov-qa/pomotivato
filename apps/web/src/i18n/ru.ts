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

  "kanban.column-backlog": "Бэклог",
  "kanban.column-planned": "Запланировано",
  "kanban.column-doing": "В работе",
  "kanban.column-done": "Готово",
  "kanban.card-grip": "Перетащить карточку",
  "kanban.conflict-moved-back": "Такой переход запрещён — карточка вернулась.",
  "kanban.create-title": "Новая задача",
  "kanban.create-placeholder": "Что нужно сделать?",
  "kanban.create-submit": "Добавить",
  "kanban.field-type": "Тип",
  "kanban.task-type-normal": "Обычная",
  "kanban.task-type-study": "Учёба",
  "kanban.task-type-habit": "Привычка",
  "kanban.field-quadrant": "Квадрат",
  "kanban.quadrant-plain": "Не важно · не срочно",
  "kanban.quadrant-important": "Важно · не срочно",
  "kanban.quadrant-urgent": "Срочно · не важно",
  "kanban.quadrant-both": "Важно и срочно",
  "kanban.field-blocks": "Блоков",
  "kanban.science-toggle": "Научный блок",
  "kanban.field-deadline": "Дедлайн",
  "kanban.field-when-then": "Когда → тогда",
  "kanban.field-done-criteria": "Критерий готовности",
  "kanban.field-benefit": "Зачем это",
  "kanban.field-parent": "Родительская задача",
  "kanban.parent-none": "— без родителя —",
  "kanban.delete": "Удалить",
  "kanban.planner-title": "План дня",
  "kanban.planner-empty": "Секторов пока нет. Добавь блоки у запланированных задач.",
  "kanban.planner-slot-add": "+1 блок",
  "kanban.planner-slot-remove": "−1 блок",
  "kanban.planner-sector": "Сектор",
} as const;

export type MessageKey = keyof typeof RU;

const DICTIONARIES: Record<Locale, Record<MessageKey, string>> = { ru: RU };

export function t(key: MessageKey, locale: Locale = "ru"): string {
  return DICTIONARIES[locale][key];
}
