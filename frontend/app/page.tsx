import { redirect } from "next/navigation";

/**
 * Kök sayfa — kullanıcıyı varsayılan admin rotasına yönlendirir.
 * Miço Usta auth entegrasyonunda bu sayfa JWT rolüne göre yönlendirecektir.
 */
export default function RootPage() {
  redirect("/admin/analytics");
}
