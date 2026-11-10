import { Container, Reshaped } from "reshaped";
import { BrowserRouter, Route, Routes } from "react-router-dom";

function ApplicationShell() {
  return (
    <Container width="100%">
      <main className="app-shell">
        <header>
          <h1>Chore Tracker</h1>
          <p>Family chore tracker</p>
        </header>
      </main>
    </Container>
  );
}

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
          <Route path="/" element={<ApplicationShell />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </BrowserRouter>
    </Reshaped>
  );
}