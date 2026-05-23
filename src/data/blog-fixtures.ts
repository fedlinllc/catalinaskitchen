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

export const blogFixtures = [
  {
    fields: {
      slug: "eating-well-on-a-budget",
      title: "Eating Well on a Budget",
      excerpt: "Healthy food doesn't have to be expensive. Here are our favorite tips for stretching your grocery dollars without sacrificing nutrition or flavor.",
      publishedDate: "2025-04-01",
      content: p("Full post coming soon."),
      featuredImage: undefined,
      tags: ["nutrition", "budget"],
    },
  },
  {
    fields: {
      slug: "meal-prep-101",
      title: "Meal Prep 101: Set Yourself Up for the Week",
      excerpt: "A step-by-step guide to spending two hours on Sunday so you barely have to think about food Monday through Friday.",
      publishedDate: "2025-03-15",
      content: p("Full post coming soon."),
      featuredImage: undefined,
      tags: ["meal prep"],
    },
  },
  {
    fields: {
      slug: "the-power-of-herbs",
      title: "The Power of Fresh Herbs",
      excerpt: "Cilantro, parsley, basil — a handful of fresh herbs can transform a simple dish into something memorable.",
      publishedDate: "2025-02-20",
      content: p("Full post coming soon."),
      featuredImage: undefined,
      tags: ["ingredients", "tips"],
    },
  },
];

export type BlogFixture = (typeof blogFixtures)[number];
