# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Action executor for MIRA.

Receives a validated action dict and performs the corresponding database
operations, returning a human-readable result.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, cast

from mira.db.database import Database
from mira.db.helpers import fold_text
from mira.db.money import MONEY_ZERO, Money, money_to_decimal

# ---------------------------------------------------------------------------
# Category matching constants
# ---------------------------------------------------------------------------

# Minimum score (0–1) needed to accept a fuzzy category match.
_CATEGORY_MATCH_THRESHOLD = 0.60

# Input strings shorter than this (after normalization) are never matched.
_CATEGORY_MIN_INPUT_LENGTH = 3

# Maps fold_text(input keyword) → frozenset of fold_text(canonical names in
# all supported languages) for the corresponding category.  This drives
# cross-language synonym resolution before the generic fuzzy fallback.
#
# Keys cover common terms the AI parser is likely to emit in English *and*
# Spanish.  Values are the normalised forms of the category names as they
# appear in the seed catalog (both "en" and "es" variants).
_CATEGORY_SYNONYMS: dict[str, frozenset[str]] = {
    # ── Income: salary_compensation ──────────────────────────────────────
    # "Salary and Compensation" (en) / "Salario y Remuneracion" (es)
    "salary": frozenset({"salary and compensation", "salario y remuneracion"}),
    "salaries": frozenset({"salary and compensation", "salario y remuneracion"}),
    "wage": frozenset({"salary and compensation", "salario y remuneracion"}),
    "wages": frozenset({"salary and compensation", "salario y remuneracion"}),
    "salario": frozenset({"salary and compensation", "salario y remuneracion"}),
    "sueldo": frozenset({"salary and compensation", "salario y remuneracion"}),
    "remuneracion": frozenset({"salary and compensation", "salario y remuneracion"}),
    # ── Income: net_salary ───────────────────────────────────────────────
    # "Net Salary (Payroll)" / "Sueldo Neto (Nomina)"
    "payroll": frozenset({"net salary payroll", "sueldo neto nomina"}),
    "paycheck": frozenset({"net salary payroll", "sueldo neto nomina"}),
    "nomina": frozenset({"net salary payroll", "sueldo neto nomina"}),
    # ── Income: bonuses ──────────────────────────────────────────────────
    # "Bonuses and Commissions" / "Bonos y Comisiones"
    "bonus": frozenset({"bonuses and commissions", "bonos y comisiones"}),
    "bonuses": frozenset({"bonuses and commissions", "bonos y comisiones"}),
    "commission": frozenset({"bonuses and commissions", "bonos y comisiones"}),
    "commissions": frozenset({"bonuses and commissions", "bonos y comisiones"}),
    "bono": frozenset({"bonuses and commissions", "bonos y comisiones"}),
    "comision": frozenset({"bonuses and commissions", "bonos y comisiones"}),
    "comisiones": frozenset({"bonuses and commissions", "bonos y comisiones"}),
    # ── Income: services_sales ───────────────────────────────────────────
    # "Services and Sales" / "Servicios y Ventas"
    "services": frozenset({"services and sales", "servicios y ventas"}),
    "sales": frozenset({"services and sales", "servicios y ventas"}),
    "servicios": frozenset({"services and sales", "servicios y ventas"}),
    "ventas": frozenset({"services and sales", "servicios y ventas"}),
    # ── Income: freelance ────────────────────────────────────────────────
    # "Freelance Fees" / "Honorarios Freelance"
    "freelance": frozenset({"freelance fees", "honorarios freelance"}),
    "consulting": frozenset({"freelance fees", "honorarios freelance"}),
    "consultant": frozenset({"freelance fees", "honorarios freelance"}),
    "honorarios": frozenset({"freelance fees", "honorarios freelance"}),
    "consultoria": frozenset({"freelance fees", "honorarios freelance"}),
    # ── Income: rent_interest ────────────────────────────────────────────
    # "Rent and Interest" / "Rentas e Intereses"
    "rentas": frozenset({"rent and interest", "rentas e intereses"}),
    # ── Income: rent_collected ───────────────────────────────────────────
    # "Rent Collected" / "Alquileres Cobrados"
    "rent collected": frozenset({"rent collected", "alquileres cobrados"}),
    "rental income": frozenset({"rent collected", "alquileres cobrados"}),
    "alquiler cobrado": frozenset({"rent collected", "alquileres cobrados"}),
    # ── Income: investment_interest ──────────────────────────────────────
    # "Investment Interest" / "Intereses de Inversiones"
    "interest": frozenset({"investment interest", "intereses de inversiones"}),
    "dividend": frozenset({"investment interest", "intereses de inversiones"}),
    "dividends": frozenset({"investment interest", "intereses de inversiones"}),
    "intereses": frozenset({"investment interest", "intereses de inversiones"}),
    "dividendos": frozenset({"investment interest", "intereses de inversiones"}),
    # ── Income: overtime_tips ────────────────────────────────────────────
    # "Overtime and Tips" / "Horas Extra y Propinas"
    "overtime": frozenset({"overtime and tips", "horas extra y propinas"}),
    "tips": frozenset({"overtime and tips", "horas extra y propinas"}),
    "tip": frozenset({"overtime and tips", "horas extra y propinas"}),
    "propinas": frozenset({"overtime and tips", "horas extra y propinas"}),
    "horas extra": frozenset({"overtime and tips", "horas extra y propinas"}),
    # ── Income: royalties ────────────────────────────────────────────────
    # "Royalties and Affiliates" / "Regalias y Afiliados"
    "royalties": frozenset({"royalties and affiliates", "regalias y afiliados"}),
    "royalty": frozenset({"royalties and affiliates", "regalias y afiliados"}),
    "regalias": frozenset({"royalties and affiliates", "regalias y afiliados"}),
    "afiliados": frozenset({"royalties and affiliates", "regalias y afiliados"}),
    # ── Income: reimbursements ───────────────────────────────────────────
    # "Reimbursements" / "Reembolsos"
    "reimbursement": frozenset({"reimbursements", "reembolsos"}),
    "refund": frozenset({"reimbursements", "reembolsos"}),
    "reembolso": frozenset({"reimbursements", "reembolsos"}),
    "reembolsos": frozenset({"reimbursements", "reembolsos"}),
    # ── Expense: housing ─────────────────────────────────────────────────
    # "Housing" / "Vivienda"
    "housing": frozenset({"housing", "vivienda"}),
    "home": frozenset({"housing", "vivienda"}),
    "house": frozenset({"housing", "vivienda"}),
    "vivienda": frozenset({"housing", "vivienda"}),
    "hogar": frozenset({"housing", "vivienda"}),
    "casa": frozenset({"housing", "vivienda"}),
    # ── Expense: rent_mortgage ───────────────────────────────────────────
    # "Rent or Mortgage" / "Alquiler o Hipoteca"
    "rent": frozenset({"rent or mortgage", "alquiler o hipoteca"}),
    "mortgage": frozenset({"rent or mortgage", "alquiler o hipoteca"}),
    "alquiler": frozenset({"rent or mortgage", "alquiler o hipoteca"}),
    "hipoteca": frozenset({"rent or mortgage", "alquiler o hipoteca"}),
    # ── Expense: home_maintenance ────────────────────────────────────────
    # "Maintenance and Repairs" / "Mantenimiento y Reparaciones"
    "maintenance": frozenset({"maintenance and repairs", "mantenimiento y reparaciones"}),
    "repairs": frozenset({"maintenance and repairs", "mantenimiento y reparaciones"}),
    "mantenimiento": frozenset({"maintenance and repairs", "mantenimiento y reparaciones"}),
    "reparaciones": frozenset({"maintenance and repairs", "mantenimiento y reparaciones"}),
    # ── Expense: utilities ───────────────────────────────────────────────
    # "Utilities" / "Servicios Basicos"
    "utilities": frozenset({"utilities", "servicios basicos"}),
    "servicios basicos": frozenset({"utilities", "servicios basicos"}),
    # ── Expense: electricity ─────────────────────────────────────────────
    # "Electricity, Gas and Water" / "Electricidad, Gas y Agua"
    "electricity": frozenset({"electricity gas and water", "electricidad gas y agua"}),
    "electric": frozenset({"electricity gas and water", "electricidad gas y agua"}),
    "water": frozenset({"electricity gas and water", "electricidad gas y agua"}),
    "electricidad": frozenset({"electricity gas and water", "electricidad gas y agua"}),
    "agua": frozenset({"electricity gas and water", "electricidad gas y agua"}),
    "luz": frozenset({"electricity gas and water", "electricidad gas y agua"}),
    # ── Expense: internet_phone ──────────────────────────────────────────
    # "Internet and Phone" / "Internet y Telefonia"
    "internet": frozenset({"internet and phone", "internet y telefonia"}),
    "phone": frozenset({"internet and phone", "internet y telefonia"}),
    "telecom": frozenset({"internet and phone", "internet y telefonia"}),
    "telefonia": frozenset({"internet and phone", "internet y telefonia"}),
    # ── Expense: food ────────────────────────────────────────────────────
    # "Food" / "Alimentacion"
    "food": frozenset({"food", "alimentacion"}),
    "comida": frozenset({"food", "alimentacion"}),
    "alimentacion": frozenset({"food", "alimentacion"}),
    # ── Expense: groceries ───────────────────────────────────────────────
    # "Groceries and Pantry" / "Supermercado y Despensa"
    "groceries": frozenset({"groceries and pantry", "supermercado y despensa"}),
    "grocery": frozenset({"groceries and pantry", "supermercado y despensa"}),
    "supermarket": frozenset({"groceries and pantry", "supermercado y despensa"}),
    "pantry": frozenset({"groceries and pantry", "supermercado y despensa"}),
    "supermercado": frozenset({"groceries and pantry", "supermercado y despensa"}),
    "despensa": frozenset({"groceries and pantry", "supermercado y despensa"}),
    # ── Expense: hygiene_cleaning ────────────────────────────────────────
    # "Hygiene and Cleaning Supplies" / "Articulos de Higiene y Limpieza"
    "hygiene": frozenset({"hygiene and cleaning supplies", "articulos de higiene y limpieza"}),
    "cleaning": frozenset({"hygiene and cleaning supplies", "articulos de higiene y limpieza"}),
    "higiene": frozenset({"hygiene and cleaning supplies", "articulos de higiene y limpieza"}),
    "limpieza": frozenset({"hygiene and cleaning supplies", "articulos de higiene y limpieza"}),
    # ── Expense: transport ───────────────────────────────────────────────
    # "Transport" / "Transporte"
    "transport": frozenset({"transport", "transporte"}),
    "transportation": frozenset({"transport", "transporte"}),
    "transporte": frozenset({"transport", "transporte"}),
    # ── Expense: fuel_tolls ──────────────────────────────────────────────
    # "Fuel and Tolls" / "Combustible y Peajes"
    "fuel": frozenset({"fuel and tolls", "combustible y peajes"}),
    "gasoline": frozenset({"fuel and tolls", "combustible y peajes"}),
    "tolls": frozenset({"fuel and tolls", "combustible y peajes"}),
    "combustible": frozenset({"fuel and tolls", "combustible y peajes"}),
    "gasolina": frozenset({"fuel and tolls", "combustible y peajes"}),
    "peajes": frozenset({"fuel and tolls", "combustible y peajes"}),
    # ── Expense: public_transport ────────────────────────────────────────
    # "Bus, Metro or Taxi" / "Bus, Metro o Taxi"
    "bus": frozenset({"bus metro or taxi", "bus metro o taxi"}),
    "taxi": frozenset({"bus metro or taxi", "bus metro o taxi"}),
    "uber": frozenset({"bus metro or taxi", "bus metro o taxi"}),
    "metro": frozenset({"bus metro or taxi", "bus metro o taxi"}),
    "subway": frozenset({"bus metro or taxi", "bus metro o taxi"}),
    # ── Expense: vehicle_maintenance ─────────────────────────────────────
    # "Vehicle Maintenance" / "Mantenimiento del Vehiculo"
    "car repair": frozenset({"vehicle maintenance", "mantenimiento del vehiculo"}),
    "car maintenance": frozenset({"vehicle maintenance", "mantenimiento del vehiculo"}),
    "mantenimiento del vehiculo": frozenset({"vehicle maintenance", "mantenimiento del vehiculo"}),
    # ── Expense: health ──────────────────────────────────────────────────
    # "Health" / "Salud"
    "health": frozenset({"health", "salud"}),
    "salud": frozenset({"health", "salud"}),
    # ── Expense: pharmacy ────────────────────────────────────────────────
    # "Pharmacy and Consultations" / "Farmacia y Consultas"
    "pharmacy": frozenset({"pharmacy and consultations", "farmacia y consultas"}),
    "medicine": frozenset({"pharmacy and consultations", "farmacia y consultas"}),
    "doctor": frozenset({"pharmacy and consultations", "farmacia y consultas"}),
    "medical": frozenset({"pharmacy and consultations", "farmacia y consultas"}),
    "farmacia": frozenset({"pharmacy and consultations", "farmacia y consultas"}),
    "medicamentos": frozenset({"pharmacy and consultations", "farmacia y consultas"}),
    "consultas": frozenset({"pharmacy and consultations", "farmacia y consultas"}),
    # ── Expense: health_insurance ────────────────────────────────────────
    # "Health Insurance" / "Seguro Medico"
    "health insurance": frozenset({"health insurance", "seguro medico"}),
    "seguro medico": frozenset({"health insurance", "seguro medico"}),
    "seguro de salud": frozenset({"health insurance", "seguro medico"}),
    # ── Expense: education ───────────────────────────────────────────────
    # "Education" / "Estudio"
    "education": frozenset({"education", "estudio"}),
    "school": frozenset({"education", "estudio"}),
    "estudio": frozenset({"education", "estudio"}),
    "educacion": frozenset({"education", "estudio"}),
    # ── Expense: tuition ─────────────────────────────────────────────────
    # "Tuition and Monthly Fees" / "Matriculas y Mensualidades"
    "tuition": frozenset({"tuition and monthly fees", "matriculas y mensualidades"}),
    "college": frozenset({"tuition and monthly fees", "matriculas y mensualidades"}),
    "university": frozenset({"tuition and monthly fees", "matriculas y mensualidades"}),
    "colegiatura": frozenset({"tuition and monthly fees", "matriculas y mensualidades"}),
    "matricula": frozenset({"tuition and monthly fees", "matriculas y mensualidades"}),
    # ── Expense: books_courses ───────────────────────────────────────────
    # "Books and Courses" / "Libros y Cursos"
    "books": frozenset({"books and courses", "libros y cursos"}),
    "courses": frozenset({"books and courses", "libros y cursos"}),
    "training": frozenset({"books and courses", "libros y cursos"}),
    "libros": frozenset({"books and courses", "libros y cursos"}),
    "cursos": frozenset({"books and courses", "libros y cursos"}),
    # ── Expense: insurance ───────────────────────────────────────────────
    # "Insurance" / "Seguros"
    "insurance": frozenset({"insurance", "seguros"}),
    "seguros": frozenset({"insurance", "seguros"}),
    # ── Expense: life_insurance ──────────────────────────────────────────
    # "Life Insurance" / "Seguro de Vida"
    "life insurance": frozenset({"life insurance", "seguro de vida"}),
    "seguro de vida": frozenset({"life insurance", "seguro de vida"}),
    # ── Expense: vehicle_home_insurance ──────────────────────────────────
    # "Vehicle/Home Insurance" / "Seguro de Vehiculo/Hogar"
    "car insurance": frozenset({"vehicle home insurance", "seguro de vehiculo hogar"}),
    "vehicle insurance": frozenset({"vehicle home insurance", "seguro de vehiculo hogar"}),
    "home insurance": frozenset({"vehicle home insurance", "seguro de vehiculo hogar"}),
    "seguro vehicular": frozenset({"vehicle home insurance", "seguro de vehiculo hogar"}),
    # ── Expense: debt_repayment ──────────────────────────────────────────
    # "Debt Repayment" / "Amortizacion de Deuda"
    "debt": frozenset({"debt repayment", "amortizacion de deuda"}),
    "deuda": frozenset({"debt repayment", "amortizacion de deuda"}),
    # ── Expense: credit_cards ────────────────────────────────────────────
    # "Credit Cards" / "Tarjetas de Credito"
    "credit card": frozenset({"credit cards", "tarjetas de credito"}),
    "credit cards": frozenset({"credit cards", "tarjetas de credito"}),
    "tarjeta de credito": frozenset({"credit cards", "tarjetas de credito"}),
    "tarjetas de credito": frozenset({"credit cards", "tarjetas de credito"}),
    # ── Expense: personal_loans ──────────────────────────────────────────
    # "Personal Loans" / "Prestamos Personales"
    "loan": frozenset({"personal loans", "prestamos personales"}),
    "loans": frozenset({"personal loans", "prestamos personales"}),
    "prestamo": frozenset({"personal loans", "prestamos personales"}),
    "prestamos": frozenset({"personal loans", "prestamos personales"}),
    # ── Expense: taxes_fees ──────────────────────────────────────────────
    # "Taxes and Professional Fees" / "Impuestos y Honorarios Profesionales"
    "taxes": frozenset({"taxes and professional fees", "impuestos y honorarios profesionales"}),
    "tax": frozenset({"taxes and professional fees", "impuestos y honorarios profesionales"}),
    "impuestos": frozenset({"taxes and professional fees", "impuestos y honorarios profesionales"}),
    # ── Expense: savings ─────────────────────────────────────────────────
    # "Savings" / "Ahorro"
    "savings": frozenset({"savings", "ahorro"}),
    "saving": frozenset({"savings", "ahorro"}),
    "ahorro": frozenset({"savings", "ahorro"}),
    "ahorros": frozenset({"savings", "ahorro"}),
    # ── Expense: emergency_fund ──────────────────────────────────────────
    # "Emergency Fund" / "Fondo de Emergencia"
    "emergency fund": frozenset({"emergency fund", "fondo de emergencia"}),
    "emergency": frozenset({"emergency fund", "fondo de emergencia"}),
    "fondo de emergencia": frozenset({"emergency fund", "fondo de emergencia"}),
    "fondo emergencia": frozenset({"emergency fund", "fondo de emergencia"}),
    # ── Expense: retirement ──────────────────────────────────────────────
    # "Retirement or Investments Plan" / "Plan de Retiro o Inversiones"
    "retirement": frozenset({"retirement or investments plan", "plan de retiro o inversiones"}),
    "pension": frozenset({"retirement or investments plan", "plan de retiro o inversiones"}),
    "retiro": frozenset({"retirement or investments plan", "plan de retiro o inversiones"}),
    "jubilacion": frozenset({"retirement or investments plan", "plan de retiro o inversiones"}),
    # ── Expense: investment_savings ──────────────────────────────────────
    # "Investment Savings" / "Ahorro para Inversion"
    "investment": frozenset({"investment savings", "ahorro para inversion"}),
    "inversion": frozenset({"investment savings", "ahorro para inversion"}),
    "inversiones": frozenset({"investment savings", "ahorro para inversion"}),
    "crypto": frozenset({"investment savings", "ahorro para inversion"}),
    # ── Expense: entertainment ───────────────────────────────────────────
    # "Entertainment" / "Entretenimiento"
    "entertainment": frozenset({"entertainment", "entretenimiento"}),
    "leisure": frozenset({"entertainment", "entretenimiento"}),
    "entretenimiento": frozenset({"entertainment", "entretenimiento"}),
    "ocio": frozenset({"entertainment", "entretenimiento"}),
    # ── Expense: subscriptions ───────────────────────────────────────────
    # "Subscriptions and Leisure" / "Suscripciones y Ocio"
    "subscription": frozenset({"subscriptions and leisure", "suscripciones y ocio"}),
    "subscriptions": frozenset({"subscriptions and leisure", "suscripciones y ocio"}),
    "netflix": frozenset({"subscriptions and leisure", "suscripciones y ocio"}),
    "spotify": frozenset({"subscriptions and leisure", "suscripciones y ocio"}),
    "streaming": frozenset({"subscriptions and leisure", "suscripciones y ocio"}),
    "software": frozenset({"subscriptions and leisure", "suscripciones y ocio"}),
    "membership": frozenset({"subscriptions and leisure", "suscripciones y ocio"}),
    "suscripcion": frozenset({"subscriptions and leisure", "suscripciones y ocio"}),
    "suscripciones": frozenset({"subscriptions and leisure", "suscripciones y ocio"}),
    "membresia": frozenset({"subscriptions and leisure", "suscripciones y ocio"}),
    # ── Expense: restaurants ─────────────────────────────────────────────
    # "Restaurants and Outings" / "Restaurantes y Salidas"
    "restaurant": frozenset({"restaurants and outings", "restaurantes y salidas"}),
    "restaurants": frozenset({"restaurants and outings", "restaurantes y salidas"}),
    "dining": frozenset({"restaurants and outings", "restaurantes y salidas"}),
    "eating out": frozenset({"restaurants and outings", "restaurantes y salidas"}),
    "fast food": frozenset({"restaurants and outings", "restaurantes y salidas"}),
    "delivery": frozenset({"restaurants and outings", "restaurantes y salidas"}),
    "restaurante": frozenset({"restaurants and outings", "restaurantes y salidas"}),
    "restaurantes": frozenset({"restaurants and outings", "restaurantes y salidas"}),
    "salidas": frozenset({"restaurants and outings", "restaurantes y salidas"}),
    "comida rapida": frozenset({"restaurants and outings", "restaurantes y salidas"}),
    # ── Expense: travel_vacations ────────────────────────────────────────
    # "Travel and Vacations" / "Viajes y Vacaciones"
    "travel": frozenset({"travel and vacations", "viajes y vacaciones"}),
    "vacation": frozenset({"travel and vacations", "viajes y vacaciones"}),
    "vacations": frozenset({"travel and vacations", "viajes y vacaciones"}),
    "viaje": frozenset({"travel and vacations", "viajes y vacaciones"}),
    "viajes": frozenset({"travel and vacations", "viajes y vacaciones"}),
    "vacaciones": frozenset({"travel and vacations", "viajes y vacaciones"}),
    # ── Expense: cinema_events ───────────────────────────────────────────
    # "Cinema and Events" / "Cine y Eventos"
    "cinema": frozenset({"cinema and events", "cine y eventos"}),
    "movies": frozenset({"cinema and events", "cine y eventos"}),
    "events": frozenset({"cinema and events", "cine y eventos"}),
    "cine": frozenset({"cinema and events", "cine y eventos"}),
    "eventos": frozenset({"cinema and events", "cine y eventos"}),
    # ── Expense: hobbies_games ───────────────────────────────────────────
    # "Hobbies and Games" / "Pasatiempos y Juegos"
    "hobbies": frozenset({"hobbies and games", "pasatiempos y juegos"}),
    "games": frozenset({"hobbies and games", "pasatiempos y juegos"}),
    "hobby": frozenset({"hobbies and games", "pasatiempos y juegos"}),
    "pasatiempos": frozenset({"hobbies and games", "pasatiempos y juegos"}),
    "juegos": frozenset({"hobbies and games", "pasatiempos y juegos"}),
    # ── Expense: personal_shopping ───────────────────────────────────────
    # "Personal Shopping" / "Compras Personales"
    "shopping": frozenset({"personal shopping", "compras personales"}),
    "compras": frozenset({"personal shopping", "compras personales"}),
    # ── Expense: clothing_footwear ───────────────────────────────────────
    # "Clothing and Footwear" / "Ropa y Calzado"
    "clothing": frozenset({"clothing and footwear", "ropa y calzado"}),
    "clothes": frozenset({"clothing and footwear", "ropa y calzado"}),
    "footwear": frozenset({"clothing and footwear", "ropa y calzado"}),
    "shoes": frozenset({"clothing and footwear", "ropa y calzado"}),
    "ropa": frozenset({"clothing and footwear", "ropa y calzado"}),
    "calzado": frozenset({"clothing and footwear", "ropa y calzado"}),
    "zapatos": frozenset({"clothing and footwear", "ropa y calzado"}),
    # ── Expense: electronics_accessories ────────────────────────────────
    # "Electronics and Accessories" / "Electronica y Accesorios"
    "electronics": frozenset({"electronics and accessories", "electronica y accesorios"}),
    "gadgets": frozenset({"electronics and accessories", "electronica y accesorios"}),
    "electronica": frozenset({"electronics and accessories", "electronica y accesorios"}),
    "accesorios": frozenset({"electronics and accessories", "electronica y accesorios"}),
    # ── Expense: furniture_home_goods ────────────────────────────────────
    # "Furniture and Home Goods" / "Muebles y Articulos del Hogar"
    "furniture": frozenset({"furniture and home goods", "muebles y articulos del hogar"}),
    "muebles": frozenset({"furniture and home goods", "muebles y articulos del hogar"}),
    # ── Expense: family_social ───────────────────────────────────────────
    # "Family and Social" / "Familia y Social"
    "family": frozenset({"family and social", "familia y social"}),
    "social": frozenset({"family and social", "familia y social"}),
    "familia": frozenset({"family and social", "familia y social"}),
    # ── Expense: childcare_family_support ────────────────────────────────
    # "Childcare and Family Support" / "Apoyo Familiar y Cuidado de Hijos"
    "childcare": frozenset({"childcare and family support", "apoyo familiar y cuidado de hijos"}),
    "cuidado": frozenset({"childcare and family support", "apoyo familiar y cuidado de hijos"}),
    "apoyo familiar": frozenset({"childcare and family support", "apoyo familiar y cuidado de hijos"}),
    # ── Expense: gifts_social_events ─────────────────────────────────────
    # "Gifts and Social Events" / "Regalos y Eventos Sociales"
    "gifts": frozenset({"gifts and social events", "regalos y eventos sociales"}),
    "gift": frozenset({"gifts and social events", "regalos y eventos sociales"}),
    "regalos": frozenset({"gifts and social events", "regalos y eventos sociales"}),
    "regalo": frozenset({"gifts and social events", "regalos y eventos sociales"}),
    # ── Expense: pets ────────────────────────────────────────────────────
    # "Pets" / "Mascotas"
    "pets": frozenset({"pets", "mascotas"}),
    "pet": frozenset({"pets", "mascotas"}),
    "mascotas": frozenset({"pets", "mascotas"}),
    # ── Expense: veterinarian ────────────────────────────────────────────
    # "Veterinarian" / "Veterinario"
    "vet": frozenset({"veterinarian", "veterinario"}),
    "veterinarian": frozenset({"veterinarian", "veterinario"}),
    "veterinario": frozenset({"veterinarian", "veterinario"}),
    # ── Expense: business_expenses ───────────────────────────────────────
    # "Business Expenses" / "Gastos de Negocio"
    "business": frozenset({"business expenses", "gastos de negocio"}),
    "negocio": frozenset({"business expenses", "gastos de negocio"}),
    # ── Expense: donations ───────────────────────────────────────────────
    # "Donations and Charity" / "Donaciones y Caridad"
    "donations": frozenset({"donations and charity", "donaciones y caridad"}),
    "charity": frozenset({"donations and charity", "donaciones y caridad"}),
    "donacion": frozenset({"donations and charity", "donaciones y caridad"}),
    "donaciones": frozenset({"donations and charity", "donaciones y caridad"}),
    # ── Expense: charitable_giving ───────────────────────────────────────
    # "Charitable Giving" / "Donativos y Diezmos"
    "tithe": frozenset({"charitable giving", "donativos y diezmos"}),
    "church": frozenset({"charitable giving", "donativos y diezmos"}),
    "diezmo": frozenset({"charitable giving", "donativos y diezmos"}),
    "diezmos": frozenset({"charitable giving", "donativos y diezmos"}),
    # ── Expense: miscellaneous ───────────────────────────────────────────
    # "Miscellaneous" / "Gastos Varios"
    "miscellaneous": frozenset({"miscellaneous", "gastos varios"}),
    "misc": frozenset({"miscellaneous", "gastos varios"}),
    "otros": frozenset({"miscellaneous", "gastos varios"}),
    "gastos varios": frozenset({"miscellaneous", "gastos varios"}),
    # ── Expense: fines_penalties ─────────────────────────────────────────
    # "Fines and Penalties" / "Multas y Sanciones"
    "fines": frozenset({"fines and penalties", "multas y sanciones"}),
    "fine": frozenset({"fines and penalties", "multas y sanciones"}),
    "penalty": frozenset({"fines and penalties", "multas y sanciones"}),
    "multa": frozenset({"fines and penalties", "multas y sanciones"}),
    "multas": frozenset({"fines and penalties", "multas y sanciones"}),
}


def _score_name_similarity(a: str, b: str) -> float:
    """Return a [0, 1] similarity score between two already-normalised strings.

    Uses a combination of containment and word-overlap heuristics.  Caller is
    responsible for pre-processing with :func:`fold_text`.
    """
    if a == b:
        return 1.0

    # Containment: a is a meaningful substring of b (or vice-versa)
    if a in b:
        score = 0.45 + 0.40 * (len(a) / len(b))
        return min(score, 0.90)
    if b in a:
        score = 0.45 + 0.40 * (len(b) / len(a))
        return min(score, 0.90)

    # Word-level overlap (ignore very short words that are likely stop-words)
    a_words = {w for w in a.split() if len(w) > 2}
    b_words = {w for w in b.split() if len(w) > 2}
    if a_words and b_words:
        common = a_words & b_words
        if common:
            precision = len(common) / len(a_words)
            recall = len(common) / len(b_words)
            f1 = 2 * precision * recall / (precision + recall)
            return 0.35 + 0.30 * f1  # up to 0.65

    return 0.0


def _find_best_category_match(
    input_name: str,
    all_categories: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Return the best-matching category from *all_categories* for *input_name*.

    Resolution order:
    1. Exact normalised-name match.
    2. Synonym-table lookup: if the folded input appears in
       :data:`_CATEGORY_SYNONYMS`, check whether any DB category's folded name
       is in the associated canonical-name set.
    3. Fuzzy string-similarity scoring against all category names.

    Returns ``None`` when no candidate reaches :data:`_CATEGORY_MATCH_THRESHOLD`.
    """
    if not all_categories:
        return None

    folded_input = fold_text(input_name)
    if len(folded_input) < _CATEGORY_MIN_INPUT_LENGTH:
        return None

    # 1. Exact normalised match
    for cat in all_categories:
        if fold_text(str(cat.get("name") or "")) == folded_input:
            return cat

    # 2. Synonym-table lookup
    canonical_names = _CATEGORY_SYNONYMS.get(folded_input)
    if canonical_names:
        for cat in all_categories:
            if fold_text(str(cat.get("name") or "")) in canonical_names:
                return cat

    # 3. Fuzzy similarity fallback
    best_cat: dict[str, Any] | None = None
    best_score = 0.0
    for cat in all_categories:
        score = _score_name_similarity(folded_input, fold_text(str(cat.get("name") or "")))
        if score > best_score:
            best_score = score
            best_cat = cat

    return best_cat if best_score >= _CATEGORY_MATCH_THRESHOLD else None


_CARD_REFERENCE_PATTERN = re.compile(
    r"\b(?:card|credit\s+card|tarjeta|tarjeta\s+de\s+credito|tarjeta\s+de\s+crédito|visa|mastercard|amex|american\s+express)\b",
    re.IGNORECASE,
)
_CARD_USAGE_PATTERN = re.compile(
    r"\b(?:with|using|con|usando|desde|from|on|en)\b.{0,30}"
    r"\b(?:card|credit\s+card|tarjeta|visa|mastercard|amex|american\s+express)\b",
    re.IGNORECASE,
)
_CARD_PAYMENT_PATTERN = re.compile(
    r"\b(?:abone|aboné|abonar|abono|abonaré|cancele|cancelé|cancelar|cancelo|"
    r"pay(?:ed)?\s+(?:the|my)\s+card|payment\s+(?:to|for)\s+(?:my\s+)?card|"
    r"pague|pagué|pagar|transferi|transferí|transfer(?:red)?)\b",
    re.IGNORECASE,
)
_CARD_PAYMENT_TARGET_PATTERN = re.compile(
    r"\b(?:to|a|para)\b(?:\s+(?:my|mi|the|la|el))?\s+"
    r"(?:card|credit\s+card|tarjeta|visa|mastercard|amex|american\s+express)\b",
    re.IGNORECASE,
)


@dataclass
class ActionResult:
    """The outcome of executing an action."""

    success: bool
    action: str
    message: str
    data: dict[str, Any] = field(default_factory=dict)


def _period_range(period: dict[str, Any] | None) -> tuple[str | None, str | None, str]:
    today = date.today()
    if not period:
        start = today.replace(day=1)
        return start.isoformat(), today.isoformat(), "this_month"

    preset = period.get("preset") or "this_month"
    if preset == "this_month":
        start = today.replace(day=1)
        return start.isoformat(), today.isoformat(), preset
    if preset == "last_month":
        first_this_month = today.replace(day=1)
        last_prev_month = first_this_month - timedelta(days=1)
        start_prev = last_prev_month.replace(day=1)
        return start_prev.isoformat(), last_prev_month.isoformat(), preset
    if preset == "last_week":
        start = today - timedelta(days=7)
        return start.isoformat(), today.isoformat(), preset
    if preset == "last_2_months":
        approx_start = today - timedelta(days=60)
        return approx_start.isoformat(), today.isoformat(), preset
    if preset == "last_3_months":
        approx_start = today - timedelta(days=90)
        return approx_start.isoformat(), today.isoformat(), preset
    if preset == "last_6_months":
        approx_start = today - timedelta(days=180)
        return approx_start.isoformat(), today.isoformat(), preset
    if preset == "this_year":
        return date(today.year, 1, 1).isoformat(), today.isoformat(), preset
    if preset == "all_time":
        return None, today.isoformat(), preset
    if preset == "custom":
        return period.get("from"), period.get("to"), preset

    start = today.replace(day=1)
    return start.isoformat(), today.isoformat(), "this_month"


def _format_money(value: Any) -> str:
    amount = money_to_decimal(value) or MONEY_ZERO
    return f"{amount:.2f}"


def _compute_summary(db: Database, transactions: list[dict[str, Any]]) -> dict[str, Money]:
    summary = db.report.summarize_financials(transactions)
    return {
        "total_income": summary["income"],
        "total_expenses": summary["expense"],
        "savings": summary["savings"],
        "net": summary["net"],
    }


class Executor:
    """Executes structured MIRA actions against the database."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def execute(self, action: dict[str, Any]) -> ActionResult:
        """Execute *action* and return an :class:`ActionResult`."""
        action_name = action.get("action", "none")
        handlers = {
            "add_income": self._add_income,
            "add_expense": self._add_expense,
            "report": self._report,
            "data_analysis": self._data_analysis,
            "none": self._none,
        }
        handler = handlers.get(action_name, self._none)
        return handler(action)

    def _mentioned_accounts(
        self,
        text: str | None,
        *,
        account_types: tuple[str, ...] | None = None,
    ) -> list[dict[str, Any]]:
        if not text:
            return []
        return self._db.account.find_mentions(text, account_types=account_types)

    def _resolve_known_account(
        self,
        requested_name: str | None,
        *,
        account_types: tuple[str, ...] | None = None,
    ) -> dict[str, Any] | None:
        if not requested_name or not requested_name.strip():
            return None

        direct = self._db.account.find_by_name(requested_name.strip())
        if direct is not None:
            if account_types is None or str(direct.get("account_type") or "") in set(account_types):
                return direct
            return None

        mentioned = self._mentioned_accounts(requested_name, account_types=account_types)
        if len(mentioned) == 1:
            return mentioned[0]
        return None

    def _default_account(self, *, account_types: tuple[str, ...] | None = None) -> dict[str, Any] | None:
        default = self._db.account.get_default()
        if default is not None:
            if account_types is None or str(default.get("account_type") or "") in set(account_types):
                return default

        candidates = self._db.account.list(account_types)
        if len(candidates) == 1:
            return candidates[0]
        return None

    def _resolve_account(
        self,
        requested_name: str | None,
        *,
        raw_text: str | None = None,
        account_types: tuple[str, ...] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """Resolve the account for a transaction.

        Accounts are **never** created automatically by the executor – only the
        user may create new accounts.  Resolution order:

        1. Direct lookup of *requested_name* in the database.
        2. Account mentioned anywhere in *raw_text*.
        3. The system default account (``is_default=True`` or the only account).
        """
        known = self._resolve_known_account(requested_name, account_types=account_types)
        if known is not None:
            return str(known.get("name") or requested_name or ""), known

        mentioned = self._mentioned_accounts(raw_text, account_types=account_types)
        if len(mentioned) == 1:
            return str(mentioned[0].get("name") or ""), mentioned[0]

        default = self._default_account(account_types=account_types)
        if default is not None:
            return str(default.get("name") or ""), default

        context = requested_name or (raw_text[:40] if raw_text else None) or "unknown"
        raise ValueError(
            f"No matching account could be resolved for '{context}'. "
            "Please create an account in the application before adding transactions."
        )

    @staticmethod
    def _has_card_reference(text: str | None) -> bool:
        return bool(text and _CARD_REFERENCE_PATTERN.search(text))

    @staticmethod
    def _looks_like_credit_card_payment(text: str | None) -> bool:
        if not text:
            return False
        has_payment_verb = _CARD_PAYMENT_PATTERN.search(text) is not None
        has_target_reference = _CARD_PAYMENT_TARGET_PATTERN.search(text) is not None
        if not has_payment_verb and not has_target_reference:
            return False
        if not _CARD_REFERENCE_PATTERN.search(text):
            return False
        return _CARD_USAGE_PATTERN.search(text) is None

    @staticmethod
    def _looks_like_credit_card_purchase(text: str | None) -> bool:
        if not text:
            return False
        return _CARD_REFERENCE_PATTERN.search(text) is not None and _CARD_USAGE_PATTERN.search(text) is not None

    def _resolve_credit_payment_target(
        self,
        action: dict[str, Any],
    ) -> dict[str, Any] | None:
        requested = action.get("account")
        raw_text = cast(str | None, action.get("description"))
        explicit = self._resolve_known_account(cast(str | None, requested), account_types=("credit",))
        if explicit is not None:
            return explicit

        mentioned = self._mentioned_accounts(raw_text, account_types=("credit",))
        if len(mentioned) == 1:
            return mentioned[0]
        if len(mentioned) > 1:
            return None

        credit_accounts = self._db.account.list_credit()
        if self._has_card_reference(raw_text) and len(credit_accounts) == 1:
            return credit_accounts[0]
        return None

    def _resolve_credit_payment_source(self, raw_text: str | None) -> dict[str, Any] | None:
        mentioned = self._mentioned_accounts(raw_text, account_types=("bank", "cash"))
        if len(mentioned) == 1:
            return mentioned[0]
        if len(mentioned) > 1:
            return None
        return self._default_account(account_types=("bank", "cash"))

    def _maybe_record_credit_card_payment(self, action: dict[str, Any]) -> ActionResult | None:
        raw_text = cast(str | None, action.get("description"))
        if not self._looks_like_credit_card_payment(raw_text):
            return None

        target = self._resolve_credit_payment_target(action)
        if target is None:
            return ActionResult(
                success=True,
                action="none",
                message="Necesito identificar con claridad la tarjeta de crédito para registrar ese pago.",
            )

        source = self._resolve_credit_payment_source(raw_text)
        if source is None:
            return ActionResult(
                success=True,
                action="none",
                message="Necesito saber desde qué cuenta bank/cash se realizó el pago de la tarjeta.",
            )

        amount_value = action.get("converted_amount")
        if amount_value is None:
            amount_value = action.get("amount")
        if amount_value is None:
            raise ValueError("Credit card payment amount is required")
        stored_amount = money_to_decimal(cast(Any, amount_value)) or MONEY_ZERO
        debit_tx, credit_tx = self._db.transaction.record_credit_card_payment(
            from_account_id=int(source["id"]),
            credit_account_id=int(target["id"]),
            amount=stored_amount,
            description=raw_text,
            exchange_rate=action.get("exchange_rate"),
            converted_amount=action.get("converted_amount"),
        )
        return ActionResult(
            success=True,
            action="add_expense",
            message=(
                f"↔ Card payment recorded: {_format_money(action['amount'])} {action.get('base_currency', 'USD')}"
                f" to {target['name']} from {source['name']}"
            ),
            data={
                "debit_transaction": debit_tx,
                "credit_transaction": credit_tx,
                "from_account": source,
                "to_account": target,
            },
        )

    def _resolve_expense_account(self, action: dict[str, Any]) -> ActionResult | tuple[str, dict[str, Any]]:
        raw_text = cast(str | None, action.get("description"))
        explicit = self._resolve_known_account(cast(str | None, action.get("account")))
        if explicit is not None:
            return str(explicit.get("name") or ""), explicit

        mentioned_credit = self._mentioned_accounts(raw_text, account_types=("credit",))
        if len(mentioned_credit) == 1 and self._has_card_reference(raw_text):
            return str(mentioned_credit[0].get("name") or ""), mentioned_credit[0]
        if len(mentioned_credit) > 1 and self._has_card_reference(raw_text):
            return ActionResult(
                success=True,
                action="none",
                message="Hay más de una tarjeta posible para ese gasto. Indica cuál cuenta credit usar.",
            )

        if self._looks_like_credit_card_purchase(raw_text):
            credit_accounts = self._db.account.list_credit()
            if len(credit_accounts) == 1:
                return str(credit_accounts[0].get("name") or ""), credit_accounts[0]
            if len(credit_accounts) > 1:
                return ActionResult(
                    success=True,
                    action="none",
                    message="Necesito saber con cuál tarjeta de crédito hiciste esa compra.",
                )

        return self._resolve_account(cast(str | None, action.get("account")), raw_text=raw_text)

    def _resolve_category(self, action: dict[str, Any], cat_type: str) -> str | None:
        """Resolve the category for a transaction without ever creating new ones.

        Resolution order:
        1. Exact case-insensitive match for the given type.
        2. Exact case-insensitive match across all types (reuse the name).
        3. :func:`_find_best_category_match` – synonym lookup + fuzzy scoring
           against all categories of *cat_type* in the database.

        Returns ``None`` when no sufficiently good match is found.  The
        executor never creates categories automatically; only the user can do
        that through the UI.
        """
        category = action.get("category")
        if not isinstance(category, str):
            return None
        normalized = category.strip()
        if not normalized:
            return None

        # 1. Exact match for the correct type
        existing_for_type = self._db.category.find_by_name(normalized, cat_type)
        if existing_for_type is not None:
            return str(existing_for_type.get("name") or normalized)

        # 2. Exact match across all types (names are globally unique)
        existing_any_type = self._db.category.find_by_name(normalized)
        if existing_any_type is not None:
            return str(existing_any_type.get("name") or normalized)

        # 3. Fuzzy / synonym-based match against DB categories of this type
        all_categories = self._db.category.list(cat_type)
        best = _find_best_category_match(normalized, all_categories)
        return str(best.get("name")) if best is not None else None

    def _add_income(self, action: dict[str, Any]) -> ActionResult:
        raw_text = cast(str | None, action.get("description"))
        account_name, account = self._resolve_account(cast(str | None, action.get("account")), raw_text=raw_text)
        category_name = self._resolve_category(action, "income")
        amount_value = action.get("converted_amount")
        if amount_value is None:
            amount_value = action.get("amount")
        if amount_value is None:
            raise ValueError("Income amount is required")
        stored_amount = money_to_decimal(cast(Any, amount_value)) or MONEY_ZERO
        tx = self._db.transaction.create(
            account_id=account["id"],
            tx_type="income",
            amount=stored_amount,
            description=action.get("description"),
            category=category_name,
            exchange_rate=action.get("exchange_rate"),
            converted_amount=action.get("converted_amount"),
            source="nl_assistant",
        )
        msg = (
            f"✅ Income recorded: {_format_money(action['amount'])} {action.get('base_currency', 'USD')}"
            f" (converted: {_format_money(stored_amount)})"
            f"{' – ' + action['description'] if action.get('description') else ''}"
            f" (account: {account_name})"
        )
        return ActionResult(
            success=True,
            action="add_income",
            message=msg,
            data={"transaction": tx, "account": account},
        )

    def _add_expense(self, action: dict[str, Any]) -> ActionResult:
        payment_result = self._maybe_record_credit_card_payment(action)
        if payment_result is not None:
            return payment_result

        resolved_account = self._resolve_expense_account(action)
        if isinstance(resolved_account, ActionResult):
            return resolved_account
        account_name, account = resolved_account
        category_name = self._resolve_category(action, "expense")
        amount_value = action.get("converted_amount")
        if amount_value is None:
            amount_value = action.get("amount")
        if amount_value is None:
            raise ValueError("Expense amount is required")
        stored_amount = money_to_decimal(cast(Any, amount_value)) or MONEY_ZERO
        tx = self._db.transaction.create(
            account_id=account["id"],
            tx_type="expense",
            amount=stored_amount,
            description=action.get("description"),
            category=category_name,
            exchange_rate=action.get("exchange_rate"),
            converted_amount=action.get("converted_amount"),
            source="nl_assistant",
        )
        msg = (
            f"💸 Expense recorded: {_format_money(action['amount'])} {action.get('base_currency', 'USD')}"
            f" (converted: {_format_money(stored_amount)})"
            f"{' – ' + action['description'] if action.get('description') else ''}"
            f" (account: {account_name})"
        )
        return ActionResult(
            success=True,
            action="add_expense",
            message=msg,
            data={"transaction": tx, "account": account},
        )

    def _report(self, action: dict[str, Any]) -> ActionResult:
        report_type = action.get("report_type") or "summary"
        since_date, until_date, period_preset = _period_range(action.get("period"))
        filters = action.get("filters") or {}

        categories = filters.get("categories") or []
        account_names = filters.get("accounts") or []
        search_text = filters.get("text")
        min_amount = filters.get("min_amount")
        max_amount = filters.get("max_amount")

        tx_type = None
        if report_type == "expenses":
            tx_type = "expense"
        elif report_type == "incomes":
            tx_type = "income"

        single_account_id: int | None = None
        multi_account_ids: set[int] = set()
        for account_name in account_names:
            account = self._db.account.find_by_name(account_name)
            if account is not None:
                multi_account_ids.add(int(account["id"]))
        if len(multi_account_ids) == 1:
            # Single account — push the filter into SQL for efficiency
            single_account_id = next(iter(multi_account_ids))
            multi_account_ids = set()

        category_filter = categories[0] if len(categories) == 1 else None
        transactions = self._db.transaction.list(
            limit=1000,
            tx_type=tx_type,
            account_id=single_account_id,
            since_date=since_date,
            until_date=until_date,
            category=category_filter,
            search=search_text,
            min_amount=min_amount,
            max_amount=max_amount,
        )

        if multi_account_ids:
            transactions = [t for t in transactions if t.get("account_id") in multi_account_ids]
        if len(categories) > 1:
            categories_set = set(categories)
            transactions = [t for t in transactions if t.get("category") in categories_set]

        summary = _compute_summary(self._db, transactions)
        accounts = self._db.account.list()
        recent = transactions[:10]

        lines = [
            f"📊 Report ({report_type}) – period: {period_preset}",
            f"  Income:   {_format_money(summary['total_income']):>10}",
            f"  Expenses: {_format_money(summary['total_expenses']):>10}",
            f"  Savings:  {_format_money(summary['savings']):>10}",
            f"  Net:      {_format_money(summary['net']):>10}",
            f"  Transactions matched: {len(transactions)}",
            "",
            "Accounts:",
        ]
        for acc in accounts:
            lines.append(f"  {acc['name']:<20} {_format_money(acc['balance']):>10}")

        msg = "\n".join(lines)
        return ActionResult(
            success=True,
            action="report",
            message=msg,
            data={
                "report_type": report_type,
                "period": {
                    "preset": period_preset,
                    "from": since_date,
                    "to": until_date,
                },
                "filters": filters,
                "summary": summary,
                "accounts": accounts,
                "recent_transactions": recent,
                "transactions": transactions,
            },
        )

    def _none(self, action: dict[str, Any]) -> ActionResult:
        msg = action.get("message") or (
            "Disculpa, no entendí tu solicitud. "
            "Puedo ayudarte a registrar ingresos, gastos o ver tu resumen financiero."
        )
        return ActionResult(success=True, action="none", message=msg)

    def _data_analysis(self, action: dict[str, Any]) -> ActionResult:
        period = action.get("period") or {}
        msg = (
            "Abriré el reporte MIRA oficial para analizar tus datos financieros. "
            "Ahí verás el resumen y las comparativas del periodo."
        )
        return ActionResult(
            success=True,
            action="data_analysis",
            message=msg,
            data={
                "period": period,
                "filters": action.get("filters") or {},
            },
        )
