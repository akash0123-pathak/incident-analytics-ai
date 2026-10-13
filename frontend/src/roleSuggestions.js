import { IconFileText, IconSearch, IconSparkles, IconTrendingUp } from "./components/Icons.jsx";

const COMMON_DIRECTIVES = [
  ["Smart Triage", "Show critical unresolved incidents.", IconSparkles, "Prioritised active incident triage"],
  ["Generate Report", "Generate report last 90 days.", IconFileText, "Role-ready KPIs and report download"],
  ["Trend Analysis", "Show trend last 90 days.", IconTrendingUp, "Frequency, surges and velocity"],
  ["Incident Lookup", "Show all incidents.", IconSearch, "Matching incident records"],
];

export const ROLE_SUGGESTIONS = {
  engineer: {
    templates: [["Inspect active criticals", "Which critical incidents are not resolved?"], ["AWS / infrastructure deep-dive", "Show details for the AWS outage reported last month."], ["Payment service blast radius", "Which incidents affect PaymentGateway and who owns them?"]],
    quickTags: [["Critical Queue", "Show critical unresolved incidents."], ["90-Day Trend", "Show trend last 90 days."], ["Root Cause Map", "What are the most recurring root causes?"], ["PaymentGateway", "Which incidents affect PaymentGateway and who owns them?"], ["All Incidents", "Show all incidents."]],
    directives: COMMON_DIRECTIVES,
  },
  manager: {
    templates: [["Review team workload", "Which teams have the highest unresolved incident workload this quarter?"], ["Prioritise recurring causes", "What are the most recurring root causes?"], ["Assess application risk", "Which applications generated the most critical incidents this quarter?"]],
    quickTags: [["Team Workload", "Which teams have the highest unresolved incident workload this quarter?"], ["90-Day Trend", "Show the trend of open and critical incidents over the last 90 days."], ["Recurring Causes", "What are the most recurring root causes?"], ["Application Risk", "Which applications generated the most critical incidents this quarter?"], ["Operations Report", "Generate an operational incident report for the last 90 days."]],
    directives: COMMON_DIRECTIVES,
  },
  executive: {
    templates: [["Review critical business risk", "How many critical incidents were reported this quarter?"], ["Rank application risk", "Which applications represent the highest incident risk this quarter?"], ["Review strategic controls", "What are the top three recurring risks and recommended controls?"]],
    quickTags: [["Executive Report", "Generate an executive incident risk report for the last 90 days."], ["Risk Trend", "Compare incident volume over the latest 90 days with the preceding 90 days."], ["Critical Incidents", "How many critical incidents were reported this quarter?"], ["Application Risk", "Which applications represent the highest incident risk this quarter?"], ["Top Risks", "What are the top three recurring risks and recommended controls?"]],
    directives: COMMON_DIRECTIVES,
  },
};

export function getRoleSuggestions(roleId) {
  return ROLE_SUGGESTIONS[roleId] || ROLE_SUGGESTIONS.engineer;
}
