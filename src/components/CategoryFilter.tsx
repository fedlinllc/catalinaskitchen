import { useState } from "react";
import { RECIPE_CATEGORIES } from "../lib/contentful";

interface Props {
  activeCategory?: string;
}

export default function CategoryFilter({ activeCategory }: Props) {
  const [active, setActive] = useState(activeCategory ?? "all");

  function navigate(category: string) {
    setActive(category);
    const url = category === "all" ? "/recipes" : `/recipes?category=${category}`;
    window.location.href = url;
  }

  return (
    <div className="flex flex-wrap gap-2 justify-center">
      <button
        onClick={() => navigate("all")}
        className={[
          "px-4 py-1.5 rounded-full text-sm font-medium transition-colors border",
          active === "all"
            ? "bg-[#111111] text-white border-[#111111]"
            : "bg-transparent text-[#2a2a2a] border-[#d4c8bc] hover:border-[#111111] hover:text-[#111111]",
        ].join(" ")}
      >
        All
      </button>
      {RECIPE_CATEGORIES.map(({ id, label }) => (
        <button
          key={id}
          onClick={() => navigate(id)}
          className={[
            "px-4 py-1.5 rounded-full text-sm font-medium transition-colors border",
            active === id
              ? "bg-[#111111] text-white border-[#111111]"
              : "bg-transparent text-[#2a2a2a] border-[#d4c8bc] hover:border-[#111111] hover:text-[#111111]",
          ].join(" ")}
        >
          {label}
        </button>
      ))}
    </div>
  );
}
