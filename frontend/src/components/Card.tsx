import React from "react";
import "./Card.css";

export type CardVariant = "standard" | "featured" | "queue" | "queue-flagged" | "insight";

export interface CardProps {
  variant?: CardVariant;
  title?: string;
  eyebrow?: string;
  children: React.ReactNode;
  className?: string;
  style?: React.CSSProperties;
  onClick?: () => void;
}

/** Cards §4.5 — standard, featured, queue, queue-flagged, insight */
export function Card({
  variant = "standard",
  title,
  eyebrow,
  children,
  className = "",
  style,
  onClick,
}: CardProps) {
  const classes = [
    "card",
    variant === "featured" && "card-featured",
    variant === "queue" && "card-queue",
    variant === "queue-flagged" && "card-queue card-queue-flagged",
    variant === "insight" && "card-insight",
    onClick && "card-clickable",
    className,
  ]
    .filter(Boolean)
    .join(" ");

  const Tag = onClick ? "button" : "div";

  return (
    <Tag
      className={classes}
      style={style}
      onClick={onClick}
      type={onClick ? "button" : undefined}
    >
      {eyebrow && <div className="card-eyebrow eyebrow">{eyebrow}</div>}
      {title && <h3 className="card-title">{title}</h3>}
      <div className="card-body">{children}</div>
    </Tag>
  );
}
