import { Link } from "react-router-dom";

export type BreadcrumbItem = {
  label: string;
  to?: string;
};

export function Breadcrumb({ items }: { items: BreadcrumbItem[] }) {
  return (
    <nav className="breadcrumb" aria-label="面包屑">
      {items.map((item, idx) => (
        <span key={`${item.label}-${idx}`} className="breadcrumb__item">
          {idx > 0 && <span className="breadcrumb__sep">›</span>}
          {item.to ? <Link to={item.to}>{item.label}</Link> : <span>{item.label}</span>}
        </span>
      ))}
    </nav>
  );
}
