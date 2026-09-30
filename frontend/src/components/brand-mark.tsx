export function BrandMark() {
  return (
    <svg
      aria-hidden="true"
      className="h-8 w-12 shrink-0"
      viewBox="0 0 96 64"
      xmlns="http://www.w3.org/2000/svg"
    >
      <rect
        data-part="trailer"
        x="4"
        y="10"
        width="54"
        height="34"
        rx="5"
        className="fill-orange-600 stroke-slate-900"
        strokeWidth="4"
      />
      <path
        d="M13 19h36M13 27h36"
        className="stroke-orange-200"
        strokeLinecap="round"
        strokeWidth="3"
      />
      <path
        data-part="cab"
        d="M58 22h15l13 13v9H58Z"
        className="fill-white stroke-slate-900"
        strokeLinejoin="round"
        strokeWidth="4"
      />
      <path
        d="M68 27h5l8 8H68Z"
        className="fill-sky-200 stroke-slate-900"
        strokeLinejoin="round"
        strokeWidth="3"
      />
      <path d="M86 44h6" className="stroke-slate-900" strokeLinecap="round" strokeWidth="4" />
      <circle cx="82" cy="39" r="2.5" className="fill-amber-300" />
      <circle cx="22" cy="48" r="8" className="fill-slate-900" />
      <circle cx="22" cy="48" r="3" className="fill-slate-300" />
      <circle cx="71" cy="48" r="8" className="fill-slate-900" />
      <circle cx="71" cy="48" r="3" className="fill-slate-300" />
    </svg>
  );
}
