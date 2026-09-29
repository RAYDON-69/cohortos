import { ClassWorkspaceScreen } from "./screens/classes/ClassWorkspace";
import { useEffect } from "react";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { PageTransition } from "./components/PageTransition";
import { Routes, Route, Navigate } from "react-router-dom";
import {
  startConnectivityPoll,
  stopConnectivityPoll,
} from "./api/client";
import { StaffLogin, RequireAuth } from "./auth";
import { CentreSetupWizardScreen } from "./screens/setup/CentreSetupWizard";
import { TodayAttendanceScreen } from "./screens/attendance/TodayAttendance";
import { AttendanceHistoryScreen } from "./screens/attendance/AttendanceHistory";
import { AdmissionsListScreen } from "./screens/admissions/AdmissionsList";
import { BatchSettingsScreen } from "./screens/batches/BatchSettings";
import { FeesThisMonthScreen } from "./screens/fees/FeesThisMonth";
import { GreenWhiteNagListScreen } from "./screens/fees/GreenWhiteNagList";
import { ExamEntryScreen } from "./screens/exams/ExamEntry";
import { ExamAnalyticsScreen } from "./screens/exams/ExamAnalytics";
import { VaultManagementScreen } from "./screens/vault/VaultManagement";
import { StaffRolesScreen } from "./screens/settings/StaffRoles";
import { ModeSettingsScreen } from "./screens/settings/ModeSettings";
import { MessagingSettingsScreen } from "./screens/settings/MessagingSettings";
import { ConflictLogScreen } from "./screens/settings/ConflictLog";
import { BackupExportScreen } from "./screens/settings/BackupExport";
import { BiometricDevicesScreen } from "./screens/settings/BiometricDevices";
import { StorageProviderScreen } from "./screens/settings/StorageProvider";
import { SettingsHubScreen } from "./screens/settings/SettingsHub";
import { UsageMeterScreen } from "./screens/settings/UsageMeter";
import { AiKeysScreen } from "./screens/settings/AiKeys";
import { TeacherCopilotScreen } from "./screens/ai/TeacherCopilot";
import { AutomationsScreen } from "./screens/settings/Automations";
import { StudentTutorScreen } from "./screens/student/StudentTutor";
import { StudentProfileScreen } from "./screens/students/StudentProfile";
import { BatchDetailScreen } from "./screens/batches/BatchDetail";
import { SupportLegalScreen } from "./screens/support/SupportLegal";
import { ReviewQueueScreen } from "./screens/teacher/ReviewQueue";
import { FlaggedThreadsScreen } from "./screens/teacher/FlaggedThreads";
import { StyleProfileScreen } from "./screens/teacher/StyleProfile";
import { ItemBankScreen } from "./screens/teacher/ItemBank";
import { OcrAssistScreen } from "./screens/teacher/OcrAssist";
import { CohortInsightScreen } from "./screens/teacher/CohortInsight";
import { StudentHomeScreen } from "./screens/student/StudentHome";
import { StudentSolveScreen } from "./screens/student/StudentSolve";
import { StudentVaultScreen } from "./screens/student/StudentVault";
import { StudentResultsScreen } from "./screens/student/StudentResults";
import { StudentThreadsScreen } from "./screens/student/StudentThreads";
import { ParentPortalScreen } from "./screens/parent/ParentPortal";
import { FounderDashboardScreen } from "./screens/founder/FounderDashboard";
import { TenantDetailScreen } from "./screens/founder/TenantDetail";
import { ProvisionScreen } from "./screens/founder/Provision";
import { PricingScreen } from "./screens/founder/Pricing";
import "./App.css";

export default function App() {
  useEffect(() => {
    startConnectivityPoll(20000);
    return () => stopConnectivityPoll();
  }, []);

  return (
    <ErrorBoundary>
    <PageTransition>
    <Routes>
      <Route path="/login" element={<StaffLogin />} />
      <Route path="/setup" element={<RequireAuth><CentreSetupWizardScreen /></RequireAuth>} />
      <Route path="/attendance" element={<RequireAuth><TodayAttendanceScreen /></RequireAuth>} />
      <Route path="/attendance/history" element={<RequireAuth><AttendanceHistoryScreen /></RequireAuth>} />
      <Route path="/admissions" element={<RequireAuth><AdmissionsListScreen /></RequireAuth>} />
      <Route path="/batches" element={<RequireAuth><BatchSettingsScreen /></RequireAuth>} />
      <Route path="/fees" element={<RequireAuth><FeesThisMonthScreen /></RequireAuth>} />
      <Route path="/fees/nag" element={<RequireAuth><GreenWhiteNagListScreen /></RequireAuth>} />
      <Route path="/exams" element={<RequireAuth><ExamEntryScreen /></RequireAuth>} />
      <Route path="/exams/analytics" element={<RequireAuth><ExamAnalyticsScreen /></RequireAuth>} />
      <Route path="/vault" element={<RequireAuth><VaultManagementScreen /></RequireAuth>} />
      <Route path="/settings/staff" element={<RequireAuth><StaffRolesScreen /></RequireAuth>} />
      <Route path="/settings/messaging" element={<RequireAuth><MessagingSettingsScreen /></RequireAuth>} />
      <Route path="/settings/mode" element={<RequireAuth><ModeSettingsScreen /></RequireAuth>} />
      <Route path="/settings/conflicts" element={<RequireAuth><ConflictLogScreen /></RequireAuth>} />
      <Route path="/settings/backup" element={<RequireAuth><BackupExportScreen /></RequireAuth>} />
      <Route path="/settings/biometric" element={<RequireAuth><BiometricDevicesScreen /></RequireAuth>} />
      <Route path="/settings" element={<RequireAuth><SettingsHubScreen /></RequireAuth>} />
      <Route path="/settings/usage" element={<RequireAuth><UsageMeterScreen /></RequireAuth>} />
      <Route path="/ai" element={<RequireAuth><TeacherCopilotScreen /></RequireAuth>} />
      <Route path="/settings/automations" element={<RequireAuth><AutomationsScreen /></RequireAuth>} />
      <Route path="/student/tutor" element={<RequireAuth><StudentTutorScreen /></RequireAuth>} />
      <Route path="/students/:studentId" element={<RequireAuth><StudentProfileScreen /></RequireAuth>} />
      <Route path="/batches/:batchId" element={<RequireAuth><BatchDetailScreen /></RequireAuth>} />
      <Route path="/settings/ai-keys" element={<RequireAuth><AiKeysScreen /></RequireAuth>} />
      <Route path="/support" element={<RequireAuth><SupportLegalScreen /></RequireAuth>} />
      <Route path="/settings/storage" element={<RequireAuth><StorageProviderScreen /></RequireAuth>} />
      <Route path="/teacher/review" element={<RequireAuth><ReviewQueueScreen /></RequireAuth>} />
      <Route path="/teacher/threads" element={<RequireAuth><FlaggedThreadsScreen /></RequireAuth>} />
      <Route path="/teacher/style" element={<RequireAuth><StyleProfileScreen /></RequireAuth>} />
      <Route path="/teacher/item-bank" element={<RequireAuth><ItemBankScreen /></RequireAuth>} />
      <Route path="/teacher/ocr" element={<RequireAuth><OcrAssistScreen /></RequireAuth>} />
      <Route path="/teacher/insight" element={<RequireAuth><CohortInsightScreen /></RequireAuth>} />
      <Route path="/student" element={<RequireAuth><StudentHomeScreen /></RequireAuth>} />
      <Route path="/student/solve" element={<RequireAuth><StudentSolveScreen /></RequireAuth>} />
      <Route path="/student/vault" element={<RequireAuth><StudentVaultScreen /></RequireAuth>} />
      <Route path="/student/results" element={<RequireAuth><StudentResultsScreen /></RequireAuth>} />
      <Route path="/student/threads" element={<RequireAuth><StudentThreadsScreen /></RequireAuth>} />
      <Route path="/parent" element={<RequireAuth><ParentPortalScreen /></RequireAuth>} />
      <Route path="/founder" element={<RequireAuth><FounderDashboardScreen /></RequireAuth>} />
      <Route path="/founder/tenants/:tenantId" element={<RequireAuth><TenantDetailScreen /></RequireAuth>} />
      <Route path="/founder/provision" element={<RequireAuth><ProvisionScreen /></RequireAuth>} />
      <Route path="/founder/pricing" element={<RequireAuth><PricingScreen /></RequireAuth>} />
      <Route path="/" element={<Navigate to="/attendance" replace />} />
      <Route path="*" element={<Navigate to="/attendance" replace />} />
              <Route path="/classes" element={<RequireAuth><ClassWorkspaceScreen /></RequireAuth>} />
        </Routes>
    </PageTransition>
    </ErrorBoundary>
  );
}
