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
            ? "bg-[#A06820] text-white border-[#A06820]"
            : "bg-transparent text-[#5C3D1E] border-[#DDC9A0] hover:border-[#A06820] hover:text-[#A06820]",
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
              ? "bg-[#A06820] text-white border-[#A06820]"
              : "bg-transparent text-[#5C3D1E] border-[#DDC9A0] hover:border-[#A06820] hover:text-[#A06820]",
          ].join(" ")}
        >
          {label}
        </button>
      ))}
    </div>
  );
}
