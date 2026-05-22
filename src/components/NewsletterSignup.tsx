import { useState } from "react";

export default function NewsletterSignup() {
  const [email, setEmail] = useState("");
  const [status, setStatus] = useState<"idle" | "loading" | "success" | "error">("idle");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!email) return;
    setStatus("loading");
    try {
      // Replace with your newsletter provider endpoint (e.g. Mailchimp, ConvertKit)
      await new Promise((r) => setTimeout(r, 800));
      setStatus("success");
      setEmail("");
    } catch {
      setStatus("error");
    }
  }

  if (status === "success") {
    return (
      <div className="text-center py-4">
        <p className="text-[#5B8C3E] font-medium">You're in! Check your inbox for a confirmation.</p>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col sm:flex-row gap-3 max-w-md mx-auto">
      <input
        type="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        placeholder="your@email.com"
        required
        className="flex-1 px-4 py-2 rounded-lg border border-[#DDC9A0] bg-white text-[#3D2B0F] placeholder-[#9A7850] focus:outline-none focus:ring-2 focus:ring-[#A06820]"
      />
      <button
        type="submit"
        disabled={status === "loading"}
        className="bg-[#A06820] hover:bg-[#7A4E15] disabled:opacity-60 text-white font-medium px-6 py-2 rounded-lg transition-colors whitespace-nowrap"
      >
        {status === "loading" ? "Subscribing…" : "Subscribe"}
      </button>
      {status === "error" && (
        <p className="text-red-600 text-sm mt-1 sm:col-span-2">
          Something went wrong. Please try again.
        </p>
      )}
    </form>
  );
}
