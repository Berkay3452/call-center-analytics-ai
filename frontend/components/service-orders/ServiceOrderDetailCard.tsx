"use client";

import React, { useState } from "react";
import Link from "next/link";
import type { ServiceOrderDetail } from "@/lib/api/types";
import {
  formatOrderCode,
  labelOf,
  REQUEST_CATEGORY_LABELS,
  URGENCY_LABELS,
  type RequestCategory,
  type Urgency,
} from "@/lib/types";
import { ServiceOrderStatusBadge } from "./ServiceOrderStatusBadge";
import { ServiceOrderWorkflowSteps } from "./ServiceOrderWorkflowSteps";
import { ServiceOrderStatusControl } from "./ServiceOrderStatusControl";

interface ServiceOrderDetailCardProps {
  order: ServiceOrderDetail;
  onStatusUpdated?: (updated: ServiceOrderDetail) => void;
  showBackLink?: boolean;
}

export function ServiceOrderDetailCard({
  order: initialOrder,
  onStatusUpdated,
  showBackLink = false,
}: ServiceOrderDetailCardProps) {
  const [order, setOrder] = useState<ServiceOrderDetail>(initialOrder);

  const handleUpdate = (updated: ServiceOrderDetail) => {
    setOrder(updated);
    onStatusUpdated?.(updated);
  };

  const code = formatOrderCode(order.id);
  const categoryLabel = labelOf(
    REQUEST_CATEGORY_LABELS,
    order.category as RequestCategory,
  );

  return (
    <div className="space-y-6">
      {/* Üst Bar: Geri Dönüş, Kod ve Rozet */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-slate-200 pb-4">
        <div className="flex items-center gap-3">
          {showBackLink && (
            <Link
              href="/admin/service-orders"
              className="inline-flex items-center justify-center h-8 w-8 rounded-lg bg-slate-100 text-slate-600 hover:bg-slate-200 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:ring-offset-2"
              title="Servis Emirlerine Dön"
              aria-label="Servis Emirlerine Dön"
            >
              ←
            </Link>
          )}
          <div>
            <div className="flex items-center gap-2.5">
              <span className="font-mono text-xl font-extrabold text-slate-900">
                {code}
              </span>
              <ServiceOrderStatusBadge status={order.status} />
            </div>
            <p className="text-xs text-slate-500 mt-0.5">
              Oluşturulma: {new Date(order.created_at).toLocaleString("tr-TR")}
            </p>
          </div>
        </div>

        {/* Durum Değiştirme Butonu / Seçici */}
        <ServiceOrderStatusControl
          orderId={order.id}
          currentStatus={order.status}
          onStatusUpdated={handleUpdate}
        />
      </div>

      {/* İş Akışı Adımları (Stepper) */}
      <div className="rounded-xl border border-slate-200 bg-slate-50/70 p-4">
        <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-2">
          İş Emri Süreç Akışı
        </h4>
        <ServiceOrderWorkflowSteps
          currentStatus={order.status}
          createdAt={order.created_at}
          completedAt={order.completed_at}
        />
      </div>

      {/* 2 Kolonlu Bilgi Kartları: Müşteri & Tekne */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Müşteri Kartı */}
        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-xs">
          <div className="flex items-center gap-2 mb-3">
            <span className="text-lg">👤</span>
            <h3 className="text-sm font-bold text-slate-900">
              Müşteri Bilgileri
            </h3>
          </div>
          <dl className="space-y-2 text-xs">
            <div className="flex justify-between py-1 border-b border-slate-100">
              <dt className="text-slate-500">Adı Soyadı:</dt>
              <dd className="font-semibold text-slate-800">
                {order.customer.full_name}
              </dd>
            </div>
            <div className="flex justify-between py-1 border-b border-slate-100">
              <dt className="text-slate-500">Telefon:</dt>
              <dd className="font-mono font-medium text-slate-800">
                {order.customer.phone || "—"}
              </dd>
            </div>
            <div className="flex justify-between py-1 border-b border-slate-100">
              <dt className="text-slate-500">E-Posta:</dt>
              <dd className="text-slate-800">
                {order.customer.email || "—"}
              </dd>
            </div>
            <div className="flex justify-between py-1">
              <dt className="text-slate-500">Bağlı Marina:</dt>
              <dd className="font-medium text-slate-800">
                {order.customer.marina || "—"}
              </dd>
            </div>
          </dl>
        </div>

        {/* Tekne Kartı */}
        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-xs">
          <div className="flex items-center gap-2 mb-3">
            <span className="text-lg">⛵</span>
            <h3 className="text-sm font-bold text-slate-900">
              Tekne Bilgileri
            </h3>
          </div>
          <dl className="space-y-2 text-xs">
            <div className="flex justify-between py-1 border-b border-slate-100">
              <dt className="text-slate-500">Tekne Adı:</dt>
              <dd className="font-semibold text-slate-800">
                {order.boat.name}
              </dd>
            </div>
            <div className="flex justify-between py-1 border-b border-slate-100">
              <dt className="text-slate-500">Model:</dt>
              <dd className="text-slate-800">
                {order.boat.model || "—"}
              </dd>
            </div>
            <div className="flex justify-between py-1 border-b border-slate-100">
              <dt className="text-slate-500">Yapım Yılı:</dt>
              <dd className="text-slate-800">
                {order.boat.year || "—"}
              </dd>
            </div>
            <div className="flex justify-between py-1">
              <dt className="text-slate-500">Bulunduğu Marina:</dt>
              <dd className="font-medium text-slate-800">
                {order.boat.marina || "—"}
              </dd>
            </div>
          </dl>
        </div>
      </div>

      {/* Servis & Görevli Usta Kartı */}
      <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-xs space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 border-b border-slate-100 pb-3">
          <div className="flex items-center gap-2">
            <span className="text-lg">🔧</span>
            <h3 className="text-sm font-bold text-slate-900">
              Servis & Görev Tanımı
            </h3>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-500">Kategori:</span>
            <span className="rounded-md bg-slate-100 px-2.5 py-0.5 text-xs font-semibold text-slate-700 border border-slate-200">
              {categoryLabel}
            </span>
          </div>
        </div>

        <div>
          <span className="text-xs font-semibold text-slate-500">
            Açıklama / İş Emri Notu:
          </span>
          <p className="mt-1 text-xs text-slate-800 bg-slate-50 p-3 rounded-lg border border-slate-100 leading-relaxed">
            {order.description || "Açıklama belirtilmemiş."}
          </p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-1 text-xs">
          <div className="rounded-lg bg-slate-50 p-2.5 border border-slate-100">
            <span className="text-[11px] text-slate-500 block mb-0.5">
              Atanan Usta:
            </span>
            <span className="font-semibold text-slate-800">
              {order.craftsman ? order.craftsman.full_name : "Henüz atanmadı"}
            </span>
            {order.craftsman?.specialty && (
              <span className="text-[10px] text-slate-500 block">
                {order.craftsman.specialty}
              </span>
            )}
          </div>

          <div className="rounded-lg bg-slate-50 p-2.5 border border-slate-100">
            <span className="text-[11px] text-slate-500 block mb-0.5">
              Planlanan Servis Zamanı:
            </span>
            <span className="font-medium text-slate-800">
              {order.scheduled_at
                ? new Date(order.scheduled_at).toLocaleString("tr-TR")
                : "Planlanmadı"}
            </span>
          </div>

          <div className="rounded-lg bg-slate-50 p-2.5 border border-slate-100">
            <span className="text-[11px] text-slate-500 block mb-0.5">
              Tamamlanma Zamanı:
            </span>
            <span className="font-medium text-slate-800">
              {order.completed_at
                ? new Date(order.completed_at).toLocaleString("tr-TR")
                : "Henüz tamamlanmadı"}
            </span>
          </div>
        </div>
      </div>

      {/* Kaynak Çağrı & CRM Önerisi Kartı (#114 GEREKSİNİMİ) */}
      {order.source_call && (
        <div className="rounded-xl border border-sky-200 bg-sky-50/50 p-5 shadow-xs space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 border-b border-sky-100 pb-3">
            <div className="flex items-center gap-2">
              <span className="text-lg">📞</span>
              <div>
                <h3 className="text-sm font-bold text-sky-950">
                  Kaynak Çağrı & CRM Öneri Kaydı
                </h3>
                <p className="text-[11px] text-sky-700">
                  Bu servis emri yapay zekâ tarafından onaylanan CRM önerisinden türetilmiştir
                </p>
              </div>
            </div>

            {/* Bağlantılar */}
            <div className="flex items-center gap-2">
              <Link
                href={`/admin/calls/${order.source_call.call_id}`}
                className="inline-flex items-center gap-1.5 rounded-lg bg-white px-3 py-1.5 text-xs font-bold text-sky-700 border border-sky-200 shadow-xs hover:bg-sky-50 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:ring-offset-2"
              >
                <span>🎙️</span>
                <span>Çağrıyı Aç</span>
              </Link>
              <Link
                href={`/admin/crm?q=${encodeURIComponent(order.customer.full_name)}`}
                className="inline-flex items-center gap-1.5 rounded-lg bg-sky-700 px-3 py-1.5 text-xs font-bold text-white shadow-xs hover:bg-sky-800 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:ring-offset-2"
              >
                <span>💡</span>
                <span>CRM Önerisine Git</span>
              </Link>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
            <div>
              <span className="font-semibold text-slate-500 block mb-0.5">
                Çağrıda Belirtilen Problem:
              </span>
              <p className="text-slate-800 bg-white/70 p-2.5 rounded-lg border border-sky-100">
                {order.source_call.problem || "—"}
              </p>
            </div>
            <div>
              <span className="font-semibold text-slate-500 block mb-0.5">
                Çağrı Özeti:
              </span>
              <p className="text-slate-800 bg-white/70 p-2.5 rounded-lg border border-sky-100">
                {order.source_call.summary || "—"}
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-4 text-xs pt-1">
            {order.source_call.urgency && (
              <div className="flex items-center gap-1.5">
                <span className="text-slate-500">Aciliyet:</span>
                <span className="font-semibold text-slate-800">
                  {labelOf(URGENCY_LABELS, order.source_call.urgency as Urgency)}
                </span>
              </div>
            )}
            {order.source_call.crm_review_note && (
              <div className="flex items-center gap-1.5">
                <span className="text-slate-500">Onay Notu:</span>
                <span className="italic text-slate-700">
                  &ldquo;{order.source_call.crm_review_note}&rdquo;
                </span>
              </div>
            )}
            {order.source_call.crm_reviewed_at && (
              <div className="flex items-center gap-1.5 text-slate-500">
                <span>Onay Tarihi:</span>
                <span>{new Date(order.source_call.crm_reviewed_at).toLocaleString("tr-TR")}</span>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
