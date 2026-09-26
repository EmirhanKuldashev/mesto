export type LayerId = "housing" | "schools" | "kindergartens" | "parks" | "transport" | "development" | "construction" | "life";

export const demoDistrict = {
  name: "Советский район",
  city: "Красноярск",
  score: 86,
  today: 84,
  future: 89,
  commute: "22 мин",
  price: "Выше среднего",
  confidence: "Демо",
  center: [93.025, 56.048] as [number, number],
  reasons: [
    "Работа, школы и зелёные зоны складываются в удобный ежедневный маршрут.",
    "В примере район показывает сильный баланс инфраструктуры и транспорта.",
    "Перспективные проекты добавляют потенциал на будущее.",
  ],
  risks: [
    "Часть показанных объектов пока только планируется.",
    "Цены в демонстрационном сценарии выше среднего.",
  ],
  categories: [
    { label: "Инфраструктура", value: 91 },
    { label: "Транспорт", value: 84 },
    { label: "Экология", value: 79 },
    { label: "Безопасность", value: 82 },
    { label: "Развитие", value: 88 },
  ],
};

export const demoScenarios = [
  {
    id: "balance",
    title: "Баланс",
    subtitle: "Всё важное в правильной пропорции",
    score: 86,
    accent: "mint",
    details: ["22 мин до работы", "Парки и школы рядом", "Уверенный темп развития"],
  },
  {
    id: "saving",
    title: "Экономия",
    subtitle: "Больше свободы в бюджете",
    score: 78,
    accent: "blue",
    details: ["Ниже ориентир по цене", "Комфортная повседневная среда", "Чуть длиннее дорога"],
  },
  {
    id: "future",
    title: "Перспектива",
    subtitle: "Ставка на то, что будет завтра",
    score: 82,
    accent: "violet",
    details: ["Новые общественные пространства", "Планируемые объекты", "Выше доля прогноза"],
  },
] as const;

export const demoLayers: { id: LayerId; label: string; color: string }[] = [
  { id: "housing", label: "ЖК", color: "#8be8d8" },
  { id: "schools", label: "Школы", color: "#f3bf7a" },
  { id: "kindergartens", label: "Детсады", color: "#f4a7c6" },
  { id: "parks", label: "Парки", color: "#75d6a3" },
  { id: "transport", label: "Транспорт", color: "#88b7ff" },
  { id: "development", label: "Развитие", color: "#d4b5ff" },
  { id: "construction", label: "Стройки", color: "#f49d82" },
  { id: "life", label: "Точки жизни", color: "#0e74ff" },
];

export const demoPlaces: { id: number; layer: LayerId; name: string; coordinates: [number, number] }[] = [
  { id: 1, layer: "housing", name: "Жилой квартал · демо", coordinates: [93.023, 56.052] },
  { id: 2, layer: "housing", name: "Новый дом · демо", coordinates: [93.055, 56.043] },
  { id: 3, layer: "schools", name: "Школа · демо", coordinates: [92.992, 56.049] },
  { id: 4, layer: "schools", name: "Школа · демо", coordinates: [93.047, 56.062] },
  { id: 5, layer: "kindergartens", name: "Детский сад · демо", coordinates: [93.007, 56.061] },
  { id: 6, layer: "parks", name: "Зелёная зона · демо", coordinates: [92.981, 56.056] },
  { id: 7, layer: "parks", name: "Парк · демо", coordinates: [93.035, 56.07] },
  { id: 8, layer: "transport", name: "Остановка · демо", coordinates: [93.028, 56.041] },
  { id: 9, layer: "transport", name: "Транспортный узел · демо", coordinates: [93.068, 56.049] },
  { id: 10, layer: "development", name: "Общественное пространство · план", coordinates: [93.004, 56.037] },
  { id: 11, layer: "construction", name: "Новый объект · план", coordinates: [93.064, 56.066] },
];
