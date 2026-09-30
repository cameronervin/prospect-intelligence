import { cn } from "@/lib/utils";

const controlBase =
  "inline-flex min-h-11 cursor-pointer items-center justify-center rounded border px-4 text-sm font-semibold transition-colors motion-reduce:transition-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-orange-600 disabled:cursor-not-allowed disabled:opacity-50";

export const buttonStyles = {
  primary: cn(
    controlBase,
    "border-slate-950 bg-slate-950 text-white hover:border-slate-800 hover:bg-slate-800",
  ),
  review: cn(
    controlBase,
    "border-orange-700 bg-orange-700 text-white hover:border-orange-800 hover:bg-orange-800",
  ),
  secondary: cn(
    controlBase,
    "border-slate-300 bg-white text-slate-950 hover:border-slate-400 hover:bg-slate-50",
  ),
  danger: cn(controlBase, "border-red-700 bg-white text-red-700 hover:bg-red-50"),
};

export const largeButton = "min-h-12 px-6 text-base";

export const linkButton =
  "inline-flex min-h-11 cursor-pointer items-center text-xs font-medium text-slate-600 underline decoration-slate-400 underline-offset-4 hover:text-slate-950 focus-visible:rounded focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-orange-600 disabled:cursor-not-allowed disabled:opacity-50";

export const iconButton =
  "inline-grid size-11 cursor-pointer place-items-center rounded text-slate-500 hover:bg-slate-100 hover:text-slate-950 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-orange-600";

export const alertStyle =
  "flex flex-col gap-1 rounded border border-red-300 bg-red-50 px-3 py-2 text-sm leading-5 text-slate-950 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-red-700";

export const fieldLabel = "mb-1 block text-xs font-semibold text-slate-600";

export const fieldStyle =
  "w-full rounded border border-slate-400 bg-white px-3 py-2 text-base leading-6 text-slate-950 focus:border-orange-600 focus:outline-none focus:ring-2 focus:ring-orange-200 read-only:bg-slate-50 aria-invalid:border-red-700 aria-invalid:ring-red-200";

export const tableHeader =
  "whitespace-nowrap py-2 pl-3 text-xs font-semibold text-slate-500 first:pl-0";

export const typeStyles = {
  wordmark: "text-base font-bold text-slate-950",
  display: "text-2xl leading-tight font-bold text-slate-950",
  heading: "text-xl leading-tight font-bold text-slate-950",
  title: "text-base font-bold text-slate-950",
  lead: "text-lg leading-6 font-semibold text-slate-950",
  section: "text-xs font-semibold tracking-wide text-slate-600",
  body: "text-sm leading-6 text-slate-950",
  utility: "text-xs leading-4 text-slate-500",
  figure: "text-2xl leading-8 font-semibold text-slate-950 tabular-nums",
};
