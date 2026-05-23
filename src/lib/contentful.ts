import { createClient } from "contentful";
import type { Asset, EntryFieldTypes, EntrySkeletonType } from "contentful";
import { blogFixtures } from "../data/blog-fixtures";
import { mealPlanFixtures } from "../data/meal-plan-fixtures";

// ── Content type skeletons ────────────────────────────────────────────────────

export interface AuthorSkeleton {
  contentTypeId: "author";
  fields: {
    name: EntryFieldTypes.Text;
    bio?: EntryFieldTypes.Text;
    photo?: EntryFieldTypes.AssetLink;
  };
}

export interface RecipeSkeleton {
  contentTypeId: "recipe";
  fields: {
    title: EntryFieldTypes.Text;
    slug: EntryFieldTypes.Text;
    excerpt?: EntryFieldTypes.Text;
    category: EntryFieldTypes.Symbol<"dinner" | "sides" | "sauces" | "breakfast" | "dessert">;
    publishedDate: EntryFieldTypes.Date;
    featuredImage?: EntryFieldTypes.AssetLink;
    ingredients: EntryFieldTypes.RichText;
    instructions: EntryFieldTypes.RichText;
    author?: EntryFieldTypes.EntryLink<AuthorSkeleton>;
    tags?: EntryFieldTypes.Array<EntryFieldTypes.Symbol>;
  };
}

export interface MealPlanSkeleton {
  contentTypeId: "mealPlan";
  fields: {
    title: EntryFieldTypes.Text;
    slug: EntryFieldTypes.Text;
    weekOf: EntryFieldTypes.Date;
    content: EntryFieldTypes.RichText;
    isCurrent: EntryFieldTypes.Boolean;
    featuredImage?: EntryFieldTypes.AssetLink;
  };
}

export interface BlogPostSkeleton {
  contentTypeId: "blogPost";
  fields: {
    title: EntryFieldTypes.Text;
    slug: EntryFieldTypes.Text;
    excerpt?: EntryFieldTypes.Text;
    publishedDate: EntryFieldTypes.Date;
    featuredImage?: EntryFieldTypes.AssetLink;
    content: EntryFieldTypes.RichText;
    author?: EntryFieldTypes.EntryLink<AuthorSkeleton>;
    tags?: EntryFieldTypes.Array<EntryFieldTypes.Symbol>;
  };
}

// ── Client ────────────────────────────────────────────────────────────────────

function getClient() {
  const space = import.meta.env.CONTENTFUL_SPACE_ID;
  const accessToken = import.meta.env.CONTENTFUL_ACCESS_TOKEN;
  if (!space || !accessToken) {
    return null;
  }
  return createClient({ space, accessToken });
}

function todayUTC(): string {
  return new Date().toISOString().slice(0, 10);
}

// ── Recipes ───────────────────────────────────────────────────────────────────

export async function getAllRecipes() {
  const client = getClient();
  if (!client) return [];
  const entries = await client.getEntries<RecipeSkeleton>({
    content_type: "recipe",
    order: ["-fields.publishedDate"],
    "fields.publishedDate[lte]": todayUTC(),
    include: 2,
  } as any);
  return entries.items;
}

export async function getRecipesByCategory(category: string) {
  const client = getClient();
  if (!client) return [];
  const entries = await client.getEntries<RecipeSkeleton>({
    content_type: "recipe",
    "fields.category": category,
    order: ["-fields.publishedDate"],
    "fields.publishedDate[lte]": todayUTC(),
    include: 2,
  } as any);
  return entries.items;
}

export async function getRecipeBySlug(slug: string) {
  const client = getClient();
  if (!client) return null;
  const entries = await client.getEntries<RecipeSkeleton>({
    content_type: "recipe",
    "fields.slug": slug,
    include: 2,
    limit: 1,
  } as any);
  return entries.items[0] ?? null;
}

// ── Meal Plans ────────────────────────────────────────────────────────────────

export async function getAllMealPlans() {
  const client = getClient();
  if (!client) return mealPlanFixtures as any[];
  const entries = await client.getEntries<MealPlanSkeleton>({
    content_type: "mealPlan",
    order: ["-fields.weekOf"],
    include: 2,
  } as any);
  return entries.items;
}

export async function getCurrentMealPlan() {
  const client = getClient();
  if (!client) return (mealPlanFixtures.find((p) => p.fields.isCurrent) ?? null) as any;
  const entries = await client.getEntries<MealPlanSkeleton>({
    content_type: "mealPlan",
    "fields.isCurrent": true,
    include: 2,
    limit: 1,
  } as any);
  return entries.items[0] ?? null;
}

export async function getMealPlanBySlug(slug: string) {
  const client = getClient();
  if (!client) return (mealPlanFixtures.find((p) => p.fields.slug === slug) ?? null) as any;
  const entries = await client.getEntries<MealPlanSkeleton>({
    content_type: "mealPlan",
    "fields.slug": slug,
    include: 2,
    limit: 1,
  } as any);
  return entries.items[0] ?? null;
}

// ── Blog Posts ────────────────────────────────────────────────────────────────

export async function getAllBlogPosts() {
  const client = getClient();
  if (!client) return blogFixtures as any[];
  const entries = await client.getEntries<BlogPostSkeleton>({
    content_type: "blogPost",
    order: ["-fields.publishedDate"],
    "fields.publishedDate[lte]": todayUTC(),
    include: 2,
  } as any);
  return entries.items;
}

export async function getBlogPostBySlug(slug: string) {
  const client = getClient();
  if (!client) return (blogFixtures.find((p) => p.fields.slug === slug) ?? null) as any;
  const entries = await client.getEntries<BlogPostSkeleton>({
    content_type: "blogPost",
    "fields.slug": slug,
    include: 2,
    limit: 1,
  } as any);
  return entries.items[0] ?? null;
}

// ── Utilities ─────────────────────────────────────────────────────────────────

export function getImageUrl(asset: Asset | undefined): string | undefined {
  if (!asset || !asset.fields.file) return undefined;
  const url = asset.fields.file.url as string;
  return url.startsWith("//") ? `https:${url}` : url;
}

export const RECIPE_CATEGORIES = [
  { id: "dinner",    label: "Dinner" },
  { id: "sides",     label: "Sides" },
  { id: "sauces",    label: "Sauces & Salsas" },
  { id: "breakfast", label: "Breakfast" },
  { id: "dessert",   label: "Dessert" },
] as const;

export type RecipeCategory = typeof RECIPE_CATEGORIES[number]["id"];
