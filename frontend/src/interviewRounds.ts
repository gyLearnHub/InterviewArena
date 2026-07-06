import type { RoundType } from "./api";

import hrAvatar from "./assets/interviewers/hr-interviewer.png";
import managerAvatar from "./assets/interviewers/manager-interviewer.png";
import resumeAvatar from "./assets/interviewers/resume-interviewer.png";
import technicalAvatar from "./assets/interviewers/technical-interviewer.png";

export type RoundMeta = {
  label: string;
  interviewer: string;
  avatar: string;
  focus: string;
};

export const orderedRoundTypes: RoundType[] = ["resume", "technical", "manager", "hr"];

export const roundMetas: Record<RoundType, RoundMeta> = {
  resume: {
    label: "简历面",
    interviewer: "简历面试官",
    avatar: resumeAvatar,
    focus: "经历核验与岗位匹配"
  },
  technical: {
    label: "技术面",
    interviewer: "技术面试官",
    avatar: technicalAvatar,
    focus: "原理、项目和工程实践"
  },
  manager: {
    label: "主管面",
    interviewer: "主管面试官",
    avatar: managerAvatar,
    focus: "目标感、协作与复盘"
  },
  hr: {
    label: "HR 面",
    interviewer: "HR 面试官",
    avatar: hrAvatar,
    focus: "动机、稳定性与期望"
  }
};

export function roundStatusText(status: string): string {
  const map: Record<string, string> = {
    pending: "待开始",
    in_progress: "进行中",
    completed: "已完成",
    finished_early: "提前结束",
    skipped: "已跳过",
    cancelled: "未完成"
  };
  return map[status] || status;
}

export function roundCardStatusText(status: string): string {
  const map: Record<string, string> = {
    pending: "未开始",
    in_progress: "进行中",
    completed: "已结束",
    finished_early: "已结束",
    skipped: "已跳过",
    cancelled: "已结束"
  };
  return map[status] || status;
}

export function resultText(value?: string): string {
  const map: Record<string, string> = {
    passed: "通过",
    pending: "待定",
    failed: "不通过"
  };
  return value ? map[value] || value : "待定";
}
