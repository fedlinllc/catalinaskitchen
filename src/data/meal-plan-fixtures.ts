const p = (text: string) => ({
  nodeType: "document" as const,
  data: {},
  content: [
    {
      nodeType: "paragraph" as const,
      data: {},
      content: [{ nodeType: "text" as const, value: text, marks: [], data: {} }],
    },
  ],
});

export const mealPlanFixtures = [
  {
    fields: {
      slug: "week-of-may-19-2025",
      title: "Week of May 19",
      weekOf: "2025-05-19",
      isCurrent: true,
      content: p("Full meal plan details coming soon."),
      featuredImage: undefined,
    },
  },
  {
    fields: {
      slug: "week-of-may-12-2025",
      title: "Week of May 12",
      weekOf: "2025-05-12",
      isCurrent: false,
      content: p("Full meal plan details coming soon."),
      featuredImage: undefined,
    },
  },
  {
    fields: {
      slug: "week-of-may-5-2025",
      title: "Week of May 5",
      weekOf: "2025-05-05",
      isCurrent: false,
      content: p("Full meal plan details coming soon."),
      featuredImage: undefined,
    },
  },
];

export type MealPlanFixture = (typeof mealPlanFixtures)[number];
