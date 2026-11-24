import { lazy } from "react";
import { Route, Routes } from "react-router";

const List = lazy(() => import("./users"));
const Detail = lazy(() => import("./user-detail"));

export default function UsersRoutes() {
  return (
    <Routes>
      <Route index element={<List />} />
      <Route path=":id" element={<Detail />} />
    </Routes>
  );
}
