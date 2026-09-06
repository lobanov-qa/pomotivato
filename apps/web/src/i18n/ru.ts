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
  "kanban.planner-empty": "Секторов пока нет. Перетащи сегодняшние задачи в «В работе».",
  "kanban.planner-slot-add": "+1 блок",
  "kanban.planner-slot-remove": "−1 блок",
  "kanban.planner-sector": "Сектор",

  "dial.aria": "Циферблат помодоро",
  "dial.phase-work": "Работа",
  "dial.phase-break": "Перерыв",
  "dial.phase-long_break": "Длинный перерыв",
  "dial.phase-idle": "Готов к старту",
  "dial.start": "Старт",
  "dial.pause": "Пауза",
  "dial.resume": "Продолжить",
  "dial.stop": "Стоп",
  "dial.skip-break": "Пропустить перерыв",
  "dial.no-plan": "Нет задач «в работе». Перетащи сегодняшние задачи в колонку «В работе».",
  "dial.plan-title": "Сегодня",
  "dial.average-score": "Средний балл",
  "dial.reviews-count": "оценок",
  "dial.paused-hint": "На паузе — время не тратится",
  "dial.disconnected": "Соединение потеряно…",
  "dial.phase-paused": "Пауза",
  "dial.next-task": "следующая:",

  "review.kick": "Блок завершён",
  "review.title": "Оцени продуктивность",
  "review.scale-min": "вяло",
  "review.scale-max": "в потоке",
  "review.comment-placeholder": "Комментарий (необязательно)",
  "review.submit": "Сохранить",
  "review.dismiss": "Позже",
  "review.error": "Оценку не принято. Попробуй ещё раз.",

  "summary.title": "Сводка дня",
  "summary.blocks": "блоков",
  "summary.focus": "фокус",
  "summary.planned": "план",
  "summary.tasks": "задач",
  "summary.min": "мин",

  "settings.section-intervals": "Интервалы",
  "settings.section-ui": "Интерфейс",
  "settings.work": "Работа, мин",
  "settings.break": "Перерыв, мин",
  "settings.long-break": "Длинный перерыв, мин",
  "settings.long-every": "Длинный каждые N блоков",
  "settings.auto-start": "Авто-старт после перерыва",
  "settings.max-in-work": "Максимум задач в работе",
  "settings.theme": "Тема",
  "settings.theme-auto": "Как в системе",
  "settings.theme-light": "Светлая",
  "settings.theme-dark": "Тёмная",
  "settings.save": "Сохранить",
  "settings.dirty": "Есть несохранённые изменения",
  "settings.error": "Не сохранено. Проверь значения.",
} as const;

export type MessageKey = keyof typeof RU;

const DICTIONARIES: Record<Locale, Record<MessageKey, string>> = { ru: RU };

export function t(key: MessageKey, locale: Locale = "ru"): string {
  return DICTIONARIES[locale][key];
}
