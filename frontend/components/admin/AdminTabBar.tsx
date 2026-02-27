"use client";

import { AdminTabConfig, AdminTabKey } from "./adminTabs";

type Props = {
  tabs: AdminTabConfig[];
  activeTab: AdminTabKey;
  onTabChange: (key: AdminTabKey) => void;
};

export function AdminTabBar({ tabs, activeTab, onTabChange }: Props) {
  return (
    <div className="flex flex-wrap gap-1 rounded-lg border border-borderTone bg-panelSoft p-1">
      {tabs.map((tab) => (
        <button
          key={tab.key}
          onClick={() => onTabChange(tab.key)}
          className={`rounded px-3 py-1.5 text-xs uppercase tracking-wider transition ${
            activeTab === tab.key
              ? "bg-accent/15 text-accent"
              : "text-textMute hover:bg-panel hover:text-textMain"
          }`}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}
