import { Container, Reshaped } from "reshaped";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { AdminPage } from "./admin/AdminPage";
import { FamilyChorePage } from "./family/FamilyChorePage";

function NotFound() {
  return (
    <Container width="100%">
      <main className="app-shell">
        <h1>Page not found</h1>
      </main>
    </Container>
  );
}

export function App() {
  return (
    <Reshaped theme="slate">
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<FamilyChorePage />} />
          <Route path="/admin" element={<AdminPage />} />
          <Route path="/admin/reports" element={<AdminPage />} />
          <Route path="/admin/reports/:weekStart" element={<AdminPage />} />
          <Route path="/admin/enroll" element={<AdminPage />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </BrowserRouter>
    </Reshaped>
  );
}
