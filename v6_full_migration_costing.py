#!/usr/bin/env python3
"""
V5 (FULL) – Multi‑Cloud Costing with Ancillary Services
FINAL – Option B (flattened compute ladders for all clouds)

This script supports:
- Azure, AWS, GCP
- PAYG, RI‑1yr, RI‑3yr, SP‑1yr, SP‑3yr (flat ladders)
- Industry (env discounts Prod=0.70, NonProd=0.85)
- Standard (no env discount multiplier)
- ESR savings (% and amount)
- Compute + Storage + All ancillary services
- OS uplift (Windows/RHEL/SUSE)
- Pandas 3.0 "to_excel" keyword‑only syntax (no FutureWarning)
- Fully compatible with updated generate_price_models.py (Option B)

Cloud provider documentation:
    • AWS Savings Plans: "Save up to 72% with a flexible pricing model"
      – distinct 1‑yr and 3‑yr compute price buckets  [1](https://aws.amazon.com/savingsplans/compute-pricing/)
    • Azure Savings Plans: 1‑year and 3‑year commitment terms for compute
      – distinct per‑term commitment rates                 [2](https://learn.microsoft.com/en-us/azure/cost-management-billing/savings-plan/choose-commitment-amount)
"""

import os, sys, json, argparse, traceback
from datetime import datetime
import pandas as pd

PROD_HOURS = 730
NONPROD_HOURS = 264

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR  = os.path.join(SCRIPT_DIR, "output")
LOGS_DIR    = os.path.join(SCRIPT_DIR, "logs")
PRICING_DIR = os.path.join(SCRIPT_DIR, "cloud-pricing")

for d in (OUTPUT_DIR, LOGS_DIR, PRICING_DIR):
    os.makedirs(d, exist_ok=True)

LOG_FILE = os.path.join(LOGS_DIR, "v5_full_migration_costing.log")


# ---------------------------------------------------------
# LOGGING
# ---------------------------------------------------------
def reset_log():
    if os.path.exists(LOG_FILE):
        try:
            os.remove(LOG_FILE)
        except:
            pass

def log(msg):
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(msg + "\n")
    print(msg)


# ---------------------------------------------------------
# BASIC HELPERS
# ---------------------------------------------------------
def money(x):
    try:
        return round(float(x), 4)
    except:
        return 0.0

def safe_get(js, path, default=None):
    cur = js
    for p in path.split("."):
        if isinstance(cur, dict) and p in cur:
            cur = cur[p]
        else:
            return default
    return cur

def load_pricing(provider, mode):
    path = os.path.join(PRICING_DIR, f"{provider.lower()}_prices_{mode}.json")
    if not os.path.exists(path):
        log(f"[WARN] Missing pricing JSON: {path}")
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
            return d if isinstance(d, dict) else {}
    except Exception as e:
        log(f"[WARN] Pricing JSON error {path}: {e}")
        return {}

def read_apps(path):
    try:
        df = pd.read_csv(path)
    except Exception as e:
        log(f"[FATAL] Cannot read input CSV: {path} ({e})")
        sys.exit(1)

    required = {"Application ID","Application Name","Application Type","R-Pattern"}
    missing = required - set(df.columns)
    if missing:
        log(f"[FATAL] Missing required columns: {missing}")
        sys.exit(1)

    # defaults
    if "OS" not in df.columns:
        df["OS"] = "Linux"
    if "Criticality" not in df.columns:
        df["Criticality"] = "Medium"
    if "User Base" not in df.columns:
        df["User Base"] = "Internal"

    return df


# ---------------------------------------------------------
# UNIVERSAL RATE RESOLVER (Option B Compatible)
# ---------------------------------------------------------
def pick_rate(pricing, key, rate_model, default=0.0):
    """
    Works with flat ladders such as:
      compute.vm.m5.large = { payg, ri_1yr, ri_3yr, sp_1yr, sp_3yr }
    Also navigates dict‑of‑dicts for other meters.
    """
    val = safe_get(pricing, key, None)
    if val is None:
        return float(default)

    # plain number
    if isinstance(val, (int,float)):
        return float(val)

    # direct ladder
    if isinstance(val, dict) and rate_model in val and isinstance(val[rate_model], (int,float)):
        return float(val[rate_model])

    # direct PAYG fallback
    if isinstance(val, dict) and "payg" in val and isinstance(val["payg"], (int,float)):
        return float(val["payg"])

    # dict of dicts
    if isinstance(val, dict):
        for nested in val.values():
            if isinstance(nested, dict) and rate_model in nested and isinstance(nested[rate_model], (int,float)):
                return float(nested[rate_model])
        for nested in val.values():
            if isinstance(nested, (int,float)):
                return float(nested)

    return float(default)


# ---------------------------------------------------------
# ENV DISCOUNT (Industry vs Standard)
# ---------------------------------------------------------
def get_env_discount(pricing, env, pricing_mode, rate_model):
    if pricing_mode == "standard":
        return 1.0

    return pick_rate(pricing, f"meta.env_discounts.{env}", "payg", default=1.0)


# ---------------------------------------------------------
# OS UPLIFT
# ---------------------------------------------------------
def os_uplift_rates(pricing, os_name, rate_model):
    os_key = str(os_name or "Linux").strip().lower()
    if os_key == "windows":
        return pick_rate(pricing, "os.windows_hour", "payg"), pick_rate(pricing, "os.windows_hour", rate_model)
    if os_key in ("rhel","redhat","red hat enterprise linux"):
        return pick_rate(pricing, "os.rhel_hour", "payg"), pick_rate(pricing, "os.rhel_hour", rate_model)
    if os_key in ("suse","sles"):
        return pick_rate(pricing, "os.suse_hour", "payg"), pick_rate(pricing, "os.suse_hour", rate_model)
    return 0.0, 0.0


# ---------------------------------------------------------
# EMIT ROW
# ---------------------------------------------------------
def emit_row(env, hours, cat, svc, cfgtext,
             unit, qty, payg_rate, model_rate,
             env_disc, rate_model, pricing_mode):

    # env_disc must be float
    if isinstance(env_disc, dict):
        env_disc = float(env_disc.get("payg", 1.0))

    payg_cost = (payg_rate or 0.0) * qty
    raw = (model_rate or 0.0) * qty
    final = raw * env_disc

    if rate_model == "payg":
        if pricing_mode == "industry":
            savings_amt = payg_cost - final
            savings_pct = (savings_amt / payg_cost * 100) if payg_cost else 0.0
        else:
            savings_amt = 0.0
            savings_pct = 0.0
    else:
        savings_amt = payg_cost - final
        savings_pct = (savings_amt / payg_cost * 100) if payg_cost else 0.0

    return {
        "Environment": env,
        "Service Category": cat,
        "Cloud Service": svc,
        "Configuration": cfgtext,
        "Pricing Model": rate_model.upper(),
        "Unit": unit,
        "Unit Rate (USD)": money(model_rate),
        "Quantity": qty,
        "Hours": hours,
        "Monthly Cost (USD)": money(payg_cost),
        "Savings (%)": money(savings_pct),
        "Savings Amount (USD)": money(savings_amt),
        "Final Monthly Cost (USD)": money(final)
    }


# ---------------------------------------------------------
# STACK SELECTION (BEST-FIT)
# ---------------------------------------------------------
def best_stack(provider, app_type, rpat):
    """
    This defines which services are selected for an app type + R‑pattern.
    LIGHT version only does compute + storage.
    FULL version covers all services (Compute, Storage, DB, Networking,
    Security, Integration, CDN, Monitoring, Messaging).
    """
    a = str(app_type).strip().lower()
    if "web + api" in a or a == "api only" or "web app" in a:
        group = "webapi"
    elif "mainframe" in a:
        group = "mainframe"
    elif "batch" in a:
        group = "batch"
    elif "desktop" in a or "edge" in a:
        group = "desktop"
    elif "analytics" in a:
        group = "analytics"
    elif "mobile" in a:
        group = "mobile"
    else:
        group = "webapi"

    stack = []

    # ====== AZURE ===================================================
    if provider=="Azure":
        if rpat=="Rehost":
            if group=="analytics":
                stack += [
                    ("Compute","Databricks",{"tier":"Premium_light"}),
                    ("Storage","Blob",{"prod_gb":500,"nonprod_gb":100})
                ]
            else:
                stack += [
                    ("Compute","AzureVM",{"instance":"D2s_v5","prod":2,"nonprod":1}),
                    ("Storage","Files",{"prod_gb":200,"nonprod_gb":50})
                ]
        elif rpat=="Replatform":
            if group in ("webapi","mobile"):
                stack += [
                    ("Compute","AppService",{"prod_sku":"P1v3","nonprod_sku":"S1"}),
                    ("Database","AzureSQL",{"shape":"GP_vcore8","nonprod":"GP_vcore2"}),
                    ("Storage","Blob",{"prod_gb":500,"nonprod_gb":100})
                ]
                if group=="mobile":
                    stack += [("Database","Cosmos",{"tier":"prod_ru2000","nonprod":"nonprod_ru1000"})]
            elif group=="desktop":
                stack += [
                    ("Compute","AKS",{"node":"D2s_v5","prod_nodes":3,"nonprod_nodes":1}),
                    ("Database","AzureSQL",{"shape":"GP_vcore8","nonprod":"GP_vcore2"})
                ]
            else:
                stack += [("Compute","AppService",{"prod_sku":"P1v3","nonprod_sku":"S1"})]

        elif rpat=="Refactor":
            if group=="batch":
                stack += [
                    ("Compute","FunctionsPremium",{"instances_prod":2,"instances_nonprod":1}),
                    ("Storage","Blob",{"prod_gb":200,"nonprod_gb":40})
                ]
            else:
                stack += [
                    ("Compute","Functions",{"prod_gbsec":200,"nonprod_gbsec":10}),
                    ("Database","AzureSQL",{"shape":"GP_vcore8","nonprod":"GP_vcore2"})
                ]

        else:  # Rewrite
            stack += [("Compute","AppService",{"prod_sku":"P1v3","nonprod_sku":"S1"})]

        # Ancillary for Azure
        if group in ("webapi","desktop","mobile"):
            stack += [
                ("Networking","AppGatewayWAF",{}),
                ("Integration","APIM",{}),
                ("Monitoring","LogAnalytics",{}),
                ("Security","KeyVault",{}),
                ("Security","Firewall",{})
            ]
        else:
            stack += [
                ("Networking","LB",{}),
                ("Monitoring","LogAnalytics",{}),
                ("Security","KeyVault",{}),
                ("Security","Firewall",{})
            ]

    # ====== AWS =======================================================
    elif provider=="AWS":
        if rpat=="Rehost":
            if group=="analytics":
                stack += [
                    ("Compute","ECS",{"node":"m5.large","prod":2,"nonprod":1}),
                    ("Storage","S3",{"prod_gb":500,"nonprod_gb":100})
                ]
            else:
                stack += [
                    ("Compute","EC2",{"instance":"m5.large","prod":2,"nonprod":1}),
                    ("Storage","EBS",{"prod_gb":200,"nonprod_gb":50})
                ]
        elif rpat=="Replatform":
            if group in ("webapi","mobile","desktop"):
                n = 3 if group=="desktop" else 2
                stack += [
                    ("Compute","ECS",{"node":"m5.large","prod":n,"nonprod":1}),
                    ("Database","RDS",{"shape":"db_m5_large"})
                ]
            else:
                stack += [("Compute","ECS",{"node":"m5.large","prod":2,"nonprod":1})]

        elif rpat=="Refactor":
            if group=="batch":
                stack += [
                    ("Compute","Lambda",{"prod_gbsec":200,"nonprod_gbsec":10}),
                    ("Storage","S3",{"prod_gb":200,"nonprod_gb":40})
                ]
            else:
                stack += [
                    ("Compute","Lambda",{"prod_gbsec":200,"nonprod_gbsec":10}),
                    ("Database","RDS",{"shape":"db_m5_large"})
                ]

        else: # Rewrite
            stack += [("Compute","EC2",{"instance":"m5.large","prod":1,"nonprod":0})]

        # AWS ancillary
        if group in ("webapi","desktop","mobile"):
            stack += [
                ("Networking","ALB",{}),
                ("Integration","APIGateway",{}),
                ("Monitoring","CloudWatch",{}),
                ("Security","SecretsManagerKMS",{}),
                ("Networking","NAT",{}),
                ("Networking","Firewall",{}),
                ("Messaging","SQS",{}),
                ("CDN","CloudFront",{"zones":1})
            ]
        else:
            stack += [
                ("Networking","ALB",{}),
                ("Monitoring","CloudWatch",{}),
                ("Security","SecretsManagerKMS",{}),
                ("Networking","NAT",{}),
                ("Networking","Firewall",{}),
                ("CDN","CloudFront",{"zones":1})
            ]

    # ====== GCP =======================================================
    else:
        if rpat=="Rehost":
            if group=="analytics":
                stack += [
                    ("Compute","CloudRun",{"proxy":True}),
                    ("Storage","GCS",{"prod_gb":500,"nonprod_gb":100})
                ]
            else:
                stack += [
                    ("Compute","GCE",{"instance":"n2-standard-2","prod":2,"nonprod":1}),
                    ("Storage","PDSSD",{"prod_gb":200,"nonprod_gb":50})
                ]
        elif rpat=="Replatform":
            if group in ("webapi","mobile"):
                stack += [
                    ("Compute","CloudRun",{"proxy":True}),
                    ("Database","CloudSQL",{"shape":"small"})
                ]
            elif group=="desktop":
                stack += [
                    ("Compute","GCE",{"instance":"n2-standard-2","prod":3,"nonprod":1}),
                    ("Database","CloudSQL",{"shape":"small"})
                ]
            else:
                stack += [("Compute","CloudRun",{"proxy":True})]

        elif rpat=="Refactor":
            if group=="batch":
                stack += [
                    ("Compute","CloudFunctions",{"prod_gbsec":200,"nonprod_gbsec":10}),
                    ("Storage","GCS",{"prod_gb":200,"nonprod_gb":40})
                ]
            else:
                stack += [
                    ("Compute","CloudFunctions",{"prod_gbsec":200,"nonprod_gbsec":10}),
                    ("Database","CloudSQL",{"shape":"small"})
                ]
        else:
            stack += [("Compute","CloudRun",{"proxy":True})]

        # GCP ancillary
        if group in ("webapi","desktop","mobile"):
            stack += [
                ("Networking","GLB",{}),
                ("Integration","APIGateway",{}),
                ("Monitoring","GCPLogging",{}),
                ("Security","SMKMSArmor",{}),
                ("Networking","CloudNAT",{}),
                ("Messaging","PubSub",{}),
                ("CDN","CloudCDN",{"zones":1})
            ]
        else:
            stack += [
                ("Networking","GLB",{}),
                ("Monitoring","GCPLogging",{}),
                ("Security","SMKMSArmor",{}),
                ("Networking","CloudNAT",{}),
                ("CDN","CloudCDN",{"zones":1})
            ]

    return stack


# ---------------------------------------------------------
# COSTING FOR EACH PROVIDER (FULL)
# ---------------------------------------------------------
def cost_stack(provider, pricing, env, hours, items, rate_model, pricing_mode, os_name):
    rows=[]
    region   = safe_get(pricing,"meta.region","")
    env_disc = get_env_discount(pricing, env, pricing_mode, rate_model)
    ing_day  = safe_get(pricing, "monitoring.ingest_gb_day.prod" if env=="Prod" else "monitoring.ingest_gb_day.nonprod", 0)
    env_key  = "prod" if env=="Prod" else "nonprod"

    for (cat, svc, cfg) in items:
        try:
            # ---------------- AZURE -------------------
            if provider=="Azure":
                if svc=="AzureVM":
                    inst = cfg["instance"]
                    cnt  = cfg["prod"] if env=="Prod" else cfg["nonprod"]

                    base_payg = pick_rate(pricing, f"compute.vm.{inst}", "payg")
                    base_rate = pick_rate(pricing, f"compute.vm.{inst}", rate_model)

                    os_p, os_r = os_uplift_rates(pricing, os_name, rate_model)
                    payg = (base_payg or 0.0) + os_p
                    rate = (base_rate or 0.0) + os_r

                    rows.append(emit_row(env,hours,cat,"Azure VMs",
                        f"Size: {inst}; Count: {cnt}; OS: {os_name}; Region: {region}",
                        "hour", cnt*hours, payg, rate, env_disc, rate_model, pricing_mode))


                # App Service
                if svc=="AppService":
                    sku = cfg["prod_sku"] if env=="Prod" else cfg["nonprod_sku"]
                    base_p = pick_rate(pricing, f"compute.appservice_hour.{sku}", "payg")
                    base_r = pick_rate(pricing, f"compute.appservice_hour.{sku}", rate_model)

                    rows.append(emit_row(env,hours,cat,"App Service",
                        f"SKU: {sku}; Region: {region}",
                        "hour", hours, base_p, base_r, env_disc, rate_model, pricing_mode))


                # AKS
                if svc=="AKS":
                    node = cfg["node"]
                    nodes= cfg["prod_nodes"] if env=="Prod" else cfg["nonprod_nodes"]

                    base_p = pick_rate(pricing, f"compute.aks_node_hour.{node}", "payg")
                    base_r = pick_rate(pricing, f"compute.aks_node_hour.{node}", rate_model)
                    os_p, os_r = os_uplift_rates(pricing, os_name, rate_model)

                    rows.append(emit_row(env,hours,cat,"AKS",
                        f"Node: {node}; Count: {nodes}; OS: {os_name}; Region: {region}",
                        "hour", nodes*hours, base_p+os_p, base_r+os_r, env_disc, rate_model, pricing_mode))


                # Azure Functions Premium
                if svc=="FunctionsPremium":
                    inst = cfg["instances_prod"] if env=="Prod" else cfg["instances_nonprod"]
                    unit_p = pick_rate(pricing, "compute.functions_premium_month_per_instance.EP1","payg")
                    unit_r = pick_rate(pricing, "compute.functions_premium_month_per_instance.EP1",rate_model)

                    rows.append(emit_row(env,hours,cat,"Azure Functions Premium",
                        f"SKU: EP1; Instances:{inst}; Region:{region}",
                        "month", inst, unit_p, unit_r, env_disc, rate_model, pricing_mode))


                # Azure Functions (consumption)
                if svc=="Functions":
                    gbsec = cfg["prod_gbsec"] if env=="Prod" else cfg["nonprod_gbsec"]
                    # 0.000016 used earlier in LIGHT version; kept the same
                    unit = 0.000016

                    rows.append(emit_row(env,hours,cat,"Azure Functions",
                        f"GB-seconds (M): {gbsec}",
                        "GB-second", gbsec*1_000_000, unit, unit, env_disc, rate_model, pricing_mode))


                # Databricks
                if svc=="Databricks":
                    key = "compute.databricks_month.Premium_light" if env=="Prod" else \
                          "compute.databricks_month.Premium_light_np"
                    p = pick_rate(pricing,key,"payg")
                    r = pick_rate(pricing,key,rate_model)

                    rows.append(emit_row(env,hours,cat,"Azure Databricks",
                        f"Tier:Premium_light; Region:{region}",
                        "month",1,p,r,env_disc,rate_model,pricing_mode))


                # Azure SQL
                if svc=="AzureSQL":
                    shape = cfg.get("shape","GP_vcore8")
                    if env!="Prod": shape = cfg.get("nonprod","GP_vcore2")

                    p = pick_rate(pricing,f"database.azure_sql_hour.{shape}","payg")
                    r = pick_rate(pricing,f"database.azure_sql_hour.{shape}",rate_model)

                    rows.append(emit_row(env,hours,"Database","Azure SQL Database",
                        f"Tier:GP; Shape:{shape}; Region:{region}",
                        "hour", hours, p, r, env_disc, rate_model, pricing_mode))


                # Cosmos DB
                if svc=="Cosmos":
                    tier = "database.cosmos_month.prod_ru2000" if env=="Prod" \
                           else "database.cosmos_month.nonprod_ru1000"
                    p = pick_rate(pricing,tier,"payg")
                    r = pick_rate(pricing,tier,rate_model)

                    rows.append(emit_row(env,hours,"Database","Cosmos DB",
                        f"Throughput:{tier.split('.')[-1]}; Region:{region}",
                        "month",1,p,r,env_disc,rate_model,pricing_mode))


                # Files
                if svc=="Files":
                    gb = cfg["prod_gb"] if env=="Prod" else cfg["nonprod_gb"]
                    p = pick_rate(pricing,"storage.files_gb_month","payg")
                    r = pick_rate(pricing,"storage.files_gb_month",rate_model)

                    rows.append(emit_row(env,hours,"Storage","Azure Files",
                        f"Capacity(GB):{gb}; Region:{region}",
                        "GB-month",gb,p,r,env_disc,rate_model,pricing_mode))


                # Blob
                if svc=="Blob":
                    gb = cfg["prod_gb"] if env=="Prod" else cfg["nonprod_gb"]
                    p = pick_rate(pricing,"storage.blob_hot_gb_month","payg")
                    r = pick_rate(pricing,"storage.blob_hot_gb_month",rate_model)

                    rows.append(emit_row(env,hours,"Storage","Blob Storage",
                        f"Tier:Hot; GB:{gb}; Region:{region}",
                        "GB-month",gb,p,r,env_disc,rate_model,pricing_mode))


                # Application Gateway
                if svc=="AppGatewayWAF":
                    p = pick_rate(pricing, f"networking.app_gateway_waf_month.{env_key}", "payg")
                    r = pick_rate(pricing, f"networking.app_gateway_waf_month.{env_key}", rate_model)

                    rows.append(emit_row(env,hours,"Networking","App Gateway (WAF)",
                        f"SKU:WAF_v2; Region:{region}",
                        "month",1,p,r,env_disc,rate_model,pricing_mode))


                # Basic Load Balancer
                if svc=="LB":
                    p = pick_rate(pricing,"networking.lb_basic_month.month","payg")
                    r = pick_rate(pricing,"networking.lb_basic_month.month",rate_model)

                    rows.append(emit_row(env,hours,"Networking","Load Balancer",
                        f"LB Basic; Region:{region}",
                        "month",1,p,r,env_disc,rate_model,pricing_mode))


                # Firewall
                if svc=="Firewall":
                    p = pick_rate(pricing,f"security.firewall_month.{env_key}","payg")
                    r = pick_rate(pricing,f"security.firewall_month.{env_key}",rate_model)

                    rows.append(emit_row(env,hours,"Networking/Security","Azure Firewall",
                        f"Standard SKU; Region:{region}",
                        "month",1,p,r,env_disc,rate_model,pricing_mode))


                # Key Vault
                if svc=="KeyVault":
                    p = pick_rate(pricing,f"security.key_vault_month.{env_key}","payg")
                    r = pick_rate(pricing,f"security.key_vault_month.{env_key}",rate_model)

                    rows.append(emit_row(env,hours,"Security","Key Vault",
                        f"Ops/month: {200000 if env=='Prod' else 50000}",
                        "month",1,p,r,env_disc,rate_model,pricing_mode))


                # APIM
                if svc=="APIM":
                    p = pick_rate(pricing,f"integration.apim_month.{env_key}","payg")
                    r = pick_rate(pricing,f"integration.apim_month.{env_key}",rate_model)

                    rows.append(emit_row(env,hours,"Integration","API Management",
                        f"Std/Basic; Region:{region}",
                        "month",1,p,r,env_disc,rate_model,pricing_mode))


                # Log Analytics
                if svc=="LogAnalytics":
                    p = pick_rate(pricing,"monitoring.log_analytics_ingest_gb","payg")
                    r = pick_rate(pricing,"monitoring.log_analytics_ingest_gb",rate_model)

                    rows.append(emit_row(env,hours,"Monitoring","Log Analytics",
                        f"IngestionGB/day:{ing_day}; Retention:30d",
                        "GB", ing_day*30, p, r, env_disc, rate_model, pricing_mode))


            # ---------------- AWS -----------------------
            if provider=="AWS":
                if svc=="EC2":
                    inst = cfg["instance"]
                    cnt  = cfg["prod"] if env=="Prod" else cfg["nonprod"]

                    base_p = pick_rate(pricing,f"compute.vm.{inst}","payg")
                    base_r = pick_rate(pricing,f"compute.vm.{inst}",rate_model)

                    os_p, os_r = os_uplift_rates(pricing, os_name, rate_model)
                    payg = (base_p or 0.0)+os_p
                    rate = (base_r or 0.0)+os_r

                    rows.append(emit_row(env,hours,cat,"EC2",
                        f"Instance:{inst}; Count:{cnt}; OS:{os_name}; Region:{region}",
                        "hour", cnt*hours, payg, rate, env_disc, rate_model, pricing_mode))


                if svc=="ECS":
                    node = cfg["node"]
                    cnt  = cfg["prod"] if env=="Prod" else cfg["nonprod"]

                    base_p = pick_rate(pricing,f"compute.ecs_node_hour.{node}","payg")
                    base_r = pick_rate(pricing,f"compute.ecs_node_hour.{node}",rate_model)
                    os_p, os_r = os_uplift_rates(pricing, os_name, rate_model)

                    rows.append(emit_row(env,hours,cat,"ECS / Beanstalk",
                        f"Node:{node}; Count:{cnt}; OS:{os_name}; Region:{region}",
                        "hour", cnt*hours, base_p+os_p, base_r+os_r, env_disc, rate_model, pricing_mode))


                if svc=="Lambda":
                    gbsec = cfg["prod_gbsec"] if env=="Prod" else cfg["nonprod_gbsec"]
                    p = pick_rate(pricing,"compute.lambda_gb_second","payg")
                    r = pick_rate(pricing,"compute.lambda_gb_second",rate_model)

                    rows.append(emit_row(env,hours,cat,"Lambda",
                        f"GB-seconds(M):{gbsec}",
                        "GB-second",gbsec*1_000_000,p,r,env_disc,rate_model,pricing_mode))


                if svc=="RDS":
                    p = pick_rate(pricing,"database.rds_hour.db_m5_large","payg")
                    r = pick_rate(pricing,"database.rds_hour.db_m5_large",rate_model)

                    rows.append(emit_row(env,hours,"Database","RDS",
                        f"Shape:db_m5_large; Region:{region}",
                        "hour",hours,p,r,env_disc,rate_model,pricing_mode))


                if svc=="EBS":
                    gb = cfg["prod_gb"] if env=="Prod" else cfg["nonprod_gb"]
                    p = pick_rate(pricing,"storage.ebs_gp3_gb_month","payg")
                    r = pick_rate(pricing,"storage.ebs_gp3_gb_month",rate_model)

                    rows.append(emit_row(env,hours,"Storage","EBS (gp3)",
                        f"GB:{gb}",
                        "GB-month",gb,p,r,env_disc,rate_model,pricing_mode))


                if svc=="S3":
                    gb = cfg["prod_gb"] if env=="Prod" else cfg["nonprod_gb"]
                    p = pick_rate(pricing,"storage.s3_standard_gb_month","payg")
                    r = pick_rate(pricing,"storage.s3_standard_gb_month",rate_model)

                    rows.append(emit_row(env,hours,"Storage","S3 Standard",
                        f"GB:{gb}",
                        "GB-month",gb,p,r,env_disc,rate_model,pricing_mode))


                if svc=="ALB":
                    alb_p = pick_rate(pricing,"networking.alb_hour","payg")
                    alb_r = pick_rate(pricing,"networking.alb_hour",rate_model)
                    lcu_p = pick_rate(pricing,"networking.alb_lcu_hour","payg")
                    lcu_r = pick_rate(pricing,"networking.alb_lcu_hour",rate_model)

                    rows.append(emit_row(env,hours,"Networking","ALB",
                        f"ALB + LCU; Region:{region}",
                        "hour", hours, alb_p+lcu_p, alb_r+lcu_r, env_disc, rate_model, pricing_mode))


                if svc=="NAT":
                    uh_p = pick_rate(pricing,"networking.nat_gateway_hour","payg")
                    uh_r = pick_rate(pricing,"networking.nat_gateway_hour",rate_model)
                    ug_p = pick_rate(pricing,"networking.nat_data_gb","payg")
                    ug_r = pick_rate(pricing,"networking.nat_data_gb",rate_model)
                    inst=1
                    data=2000 if env=="Prod" else 100

                    rows.append(emit_row(env,hours,"Networking","NAT Gateway",
                        f"DataGB:{data}; Instances:{inst}",
                        "mixed",1,
                        uh_p*hours*inst + ug_p*data,
                        uh_r*hours*inst + ug_r*data,
                        env_disc, rate_model, pricing_mode))


                if svc=="Firewall":
                    data = 200 if env=="Prod" else 50
                    p = pick_rate(pricing,"security.network_firewall_data_gb","payg")
                    r = pick_rate(pricing,"security.network_firewall_data_gb",rate_model)

                    rows.append(emit_row(env,hours,"Networking/Security","AWS Network Firewall",
                        f"DataGB:{data}",
                        "GB",data,p,r,env_disc,rate_model,pricing_mode))


                if svc=="SecretsManagerKMS":
                    sm_p = pick_rate(pricing,"security.secrets_manager_month","payg")
                    sm_r = pick_rate(pricing,"security.secrets_manager_month",rate_model)
                    kms_p= pick_rate(pricing,"security.kms_month","payg")
                    kms_r= pick_rate(pricing,"security.kms_month",rate_model)

                    rows.append(emit_row(env,hours,"Security","Secrets Manager",
                        "Monthly ops",
                        "month",1,sm_p,sm_r,env_disc,rate_model,pricing_mode))
                    rows.append(emit_row(env,hours,"Security","KMS",
                        "Monthly ops",
                        "month",1,kms_p,kms_r,env_disc,rate_model,pricing_mode))


                if svc=="CloudWatch":
                    p = pick_rate(pricing,"monitoring.cloudwatch_log_ingest_gb","payg")
                    r = pick_rate(pricing,"monitoring.cloudwatch_log_ingest_gb",rate_model)

                    rows.append(emit_row(env,hours,"Monitoring","CloudWatch",
                        f"GB/day:{ing_day}; Retention:30",
                        "GB",ing_day*30,p,r,env_disc,rate_model,pricing_mode))


                if svc=="APIGateway":
                    p = pick_rate(pricing,"integration.api_gateway_month_small","payg")
                    r = pick_rate(pricing,"integration.api_gateway_month_small",rate_model)

                    rows.append(emit_row(env,hours,"Integration","API Gateway",
                        "Small usage",
                        "month",1,p,r,env_disc,rate_model,pricing_mode))


                if svc=="SQS":
                    ops = 5 if env=="Prod" else 1
                    p = pick_rate(pricing,"integration.sqs_million_ops","payg")
                    r = pick_rate(pricing,"integration.sqs_million_ops",rate_model)

                    rows.append(emit_row(env,hours,"Messaging","SQS",
                        f"MillionOps:{ops}",
                        "million ops",ops,p,r,env_disc,rate_model,pricing_mode))


                if svc=="CloudFront":
                    egb = 500 if env=="Prod" else 50
                    u_p = pick_rate(pricing,"cdn_dns.cloudfront_egress_gb","payg")
                    u_r = pick_rate(pricing,"cdn_dns.cloudfront_egress_gb",rate_model)
                    d_p = pick_rate(pricing,"cdn_dns.route53_zone_month","payg") * (cfg.get("zones",1))
                    d_r = pick_rate(pricing,"cdn_dns.route53_zone_month",rate_model) * (cfg.get("zones",1))

                    rows.append(emit_row(env,hours,"CDN/DNS","CloudFront+Route53",
                        f"EgressGB:{egb}; Zones:{cfg.get('zones',1)}",
                        "mixed",1, u_p*egb+d_p, u_r*egb+d_r,
                        env_disc, rate_model, pricing_mode))


            # ---------------- GCP -----------------------
            if provider=="GCP":
                if svc=="GCE":
                    inst = cfg["instance"]
                    cnt  = cfg["prod"] if env=="Prod" else cfg["nonprod"]

                    base_p = pick_rate(pricing,f"compute.vm.{inst}","payg")
                    base_r = pick_rate(pricing,f"compute.vm.{inst}",rate_model)
                    os_p, os_r = os_uplift_rates(pricing, os_name, rate_model)

                    rows.append(emit_row(env,hours,cat,"Compute Engine",
                        f"Instance:{inst}; Count:{cnt}; OS:{os_name}; Region:{region}",
                        "hour", cnt*hours, base_p+os_p, base_r+os_r,
                        env_disc, rate_model, pricing_mode))


                if svc=="CloudRun":
                    p = pick_rate(pricing,"compute.cloud_run_hour","payg")
                    r = pick_rate(pricing,"compute.cloud_run_hour",rate_model)

                    rows.append(emit_row(env,hours,cat,"Cloud Run",
                        "Small proxy baseline",
                        "hour",hours,p,r,env_disc,rate_model,pricing_mode))


                if svc=="CloudFunctions":
                    gbsec = cfg["prod_gbsec"] if env=="Prod" else cfg["nonprod_gbsec"]
                    p = pick_rate(pricing,"compute.cloudfunctions_gb_second","payg")
                    r = pick_rate(pricing,"compute.cloudfunctions_gb_second",rate_model)

                    rows.append(emit_row(env,hours,cat,"Cloud Functions",
                        f"GBsec(M):{gbsec}",
                        "GB-second",gbsec*1_000_000,p,r,env_disc,rate_model,pricing_mode))


                if svc=="CloudSQL":
                    p = pick_rate(pricing,"database.cloudsql_hour_small","payg")
                    r = pick_rate(pricing,"database.cloudsql_hour_small",rate_model)

                    rows.append(emit_row(env,hours,"Database","Cloud SQL",
                        "Small shape",
                        "hour",hours,p,r,env_disc,rate_model,pricing_mode))


                if svc=="PDSSD":
                    gb = cfg["prod_gb"] if env=="Prod" else cfg["nonprod_gb"]
                    p = pick_rate(pricing,"storage.pd_ssd_gb_month","payg")
                    r = pick_rate(pricing,"storage.pd_ssd_gb_month",rate_model)

                    rows.append(emit_row(env,hours,"Storage","PD‑SSD",
                        f"GB:{gb}",
                        "GB-month",gb,p,r,env_disc,rate_model,pricing_mode))


                if svc=="GCS":
                    gb = cfg["prod_gb"] if env=="Prod" else cfg["nonprod_gb"]
                    p = pick_rate(pricing,"storage.gcs_standard_gb_month","payg")
                    r = pick_rate(pricing,"storage.gcs_standard_gb_month",rate_model)

                    rows.append(emit_row(env,hours,"Storage","GCS Standard",
                        f"GB:{gb}",
                        "GB-month",gb,p,r,env_disc,rate_model,pricing_mode))


                if svc=="GLB":
                    p = pick_rate(pricing,"networking.glb_hour","payg")
                    r = pick_rate(pricing,"networking.glb_hour",rate_model)

                    rows.append(emit_row(env,hours,"Networking","GLB",
                        "HTTP(S) LB",
                        "hour",hours,p,r,env_disc,rate_model,pricing_mode))


                if svc=="CloudNAT":
                    uh_p = pick_rate(pricing,"networking.cloud_nat_hour","payg")
                    uh_r = pick_rate(pricing,"networking.cloud_nat_hour",rate_model)
                    ug_p = pick_rate(pricing,"networking.cloud_nat_data_gb","payg")
                    ug_r = pick_rate(pricing,"networking.cloud_nat_data_gb",rate_model)

                    inst=1
                    data=2000 if env=="Prod" else 100

                    rows.append(emit_row(env,hours,"Networking","Cloud NAT",
                        f"DataGB:{data}",
                        "mixed",1,
                        uh_p*hours*inst + ug_p*data,
                        uh_r*hours*inst + ug_r*data,
                        env_disc, rate_model, pricing_mode))


                if svc=="SMKMSArmor":
                    sm_p = pick_rate(pricing,"security.secret_manager_month","payg")
                    sm_r = pick_rate(pricing,"security.secret_manager_month",rate_model)
                    kms_p= pick_rate(pricing,"security.kms_month","payg")
                    kms_r= pick_rate(pricing,"security.kms_month",rate_model)
                    ar_p = pick_rate(pricing,"security.cloud_armor_hour","payg") * hours
                    ar_r = pick_rate(pricing,"security.cloud_armor_hour",rate_model) * hours

                    rows.append(emit_row(env,hours,"Security","SecretMgr+KMS+Armor",
                        "Bundle",
                        "mixed",1,
                        sm_p + kms_p + ar_p,
                        sm_r + kms_r + ar_r,
                        env_disc, rate_model, pricing_mode))


                if svc=="GCPLogging":
                    p = pick_rate(pricing,"monitoring.logging_ingest_gb","payg")
                    r = pick_rate(pricing,"monitoring.logging_ingest_gb",rate_model)

                    rows.append(emit_row(env,hours,"Monitoring","Cloud Logging",
                        f"GB/day:{ing_day}",
                        "GB",ing_day*30,p,r,env_disc,rate_model,pricing_mode))


                if svc=="APIGateway":
                    p = pick_rate(pricing,"integration.api_gateway_month_small","payg")
                    r = pick_rate(pricing,"integration.api_gateway_month_small",rate_model)

                    rows.append(emit_row(env,hours,"Integration","API Gateway",
                        "Small usage",
                        "month",1,p,r,env_disc,rate_model,pricing_mode))


                if svc=="PubSub":
                    ops = 5 if env=="Prod" else 1
                    p = pick_rate(pricing,"integration.pubsub_million_ops","payg")
                    r = pick_rate(pricing,"integration.pubsub_million_ops",rate_model)

                    rows.append(emit_row(env,hours,"Messaging","Pub/Sub",
                        f"MillionOps:{ops}",
                        "million ops",ops,p,r,env_disc,rate_model,pricing_mode))


                if svc=="CloudCDN":
                    egb = 500 if env=="Prod" else 50
                    u_p = pick_rate(pricing,"cdn_dns.cloud_cdn_egress_gb","payg")
                    u_r = pick_rate(pricing,"cdn_dns.cloud_cdn_egress_gb",rate_model)
                    d_p = pick_rate(pricing,"cdn_dns.cloud_dns_zone_month","payg") * (cfg.get("zones",1))
                    d_r = pick_rate(pricing,"cdn_dns.cloud_dns_zone_month",rate_model) * (cfg.get("zones",1))

                    rows.append(emit_row(env,hours,"CDN/DNS","Cloud CDN+DNS",
                        f"EgressGB:{egb}; Zones:{cfg.get('zones',1)}",
                        "mixed",1,
                        u_p*egb+d_p, u_r*egb+d_r,
                        env_disc, rate_model, pricing_mode))

        except Exception as e:
            log(f"[ERROR] Cost error {provider}/{svc}/{env}: {e}")
            log(traceback.format_exc())
            continue

    return rows


# ---------------------------------------------------------
# BUILD WORKBOOK
# ---------------------------------------------------------
def build_workbook(apps_df, provider, pricing, rate_model, pricing_mode, input_file):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = os.path.splitext(os.path.basename(input_file))[0]
    outfile = os.path.join(
        OUTPUT_DIR,
        f"Cloud_Migration_{provider}_{pricing_mode}_{rate_model}_{stem}_{timestamp}.xlsx"
    )
    log(f"Starting workbook: {outfile}")

    all_rows=[]
    rationale=[]

    for _, app in apps_df.iterrows():
        aid   = app["Application ID"]
        aname = app["Application Name"]
        atype = app["Application Type"]
        rpat  = app["R-Pattern"]
        crit  = app["Criticality"]
        os_name = app.get("OS","Linux")

        items = best_stack(provider, atype, rpat)

        for env, hrs in (("Prod",PROD_HOURS), ("Non-Prod",NONPROD_HOURS)):
            stack_rows = cost_stack(provider, pricing, env, hrs, items,
                                    rate_model, pricing_mode, os_name)
            for r in stack_rows:
                r["Application ID"] = aid
                r["Application Name"] = aname
            all_rows.extend(stack_rows)

            rationale.append({
                "Application ID": aid,
                "Application Name": aname,
                "App Type": atype,
                "Environment": env,
                "R-Pattern": rpat,
                "Criticality": crit,
                "App-Level Rationale": (
                    f"{rpat} on {provider}; Ancillary + compute + storage + DB; "
                    f"Networking/Security/Integration/Monitoring included; OS uplift applied."
                )
            })

    df_svc = pd.DataFrame(all_rows)
    df_rat = pd.DataFrame(rationale)

    if df_svc.empty:
        df_svc = pd.DataFrame(columns=[
            "Application ID","Application Name","Environment","Service Category",
            "Cloud Service","Configuration","Pricing Model","Unit","Unit Rate (USD)",
            "Quantity","Hours","Monthly Cost (USD)","Savings (%)","Savings Amount (USD)",
            "Final Monthly Cost (USD)"
        ])

    data = df_svc.copy()
    if data.empty:
        df_cost  = pd.DataFrame(columns=["Application ID","Application Name","Environment",
                                         "Estimated Monthly Cost (USD)"])
        df_p_app = pd.DataFrame(columns=["Application ID","Application Name",
                                         "Estimated Monthly Cost (USD)"])
        df_p_rp  = pd.DataFrame(columns=["R-Pattern","Environment","Total Cost (USD)",
                                         "Application Count"])
        df_p_env = pd.DataFrame(columns=["Environment","Total Cost (USD)",
                                         "Application Count"])
    else:
        df_cost = (
            data.groupby(["Application ID","Application Name","Environment"])
                ["Final Monthly Cost (USD)"].sum().reset_index()
                .rename(columns={"Final Monthly Cost (USD)":"Estimated Monthly Cost (USD)"})
        )

        df_p_app = (
            data.groupby(["Application ID","Application Name"])
                ["Final Monthly Cost (USD)"].sum().reset_index()
                .rename(columns={"Final Monthly Cost (USD)":"Estimated Monthly Cost (USD)"})
        )

        tmp = apps_df[["Application ID","R-Pattern"]].drop_duplicates()
        j = data.merge(tmp, on="Application ID", how="left")

        df_p_rp = (
            j.groupby(["R-Pattern","Environment"])
             .agg(**{
                 "Total Cost (USD)":("Final Monthly Cost (USD)","sum"),
                 "Application Count":("Application ID","nunique")
             }).reset_index()
        )

        df_p_env = (
            data.groupby("Environment")
                .agg(**{
                    "Total Cost (USD)":("Final Monthly Cost (USD)","sum"),
                    "Application Count":("Application ID","nunique")
                }).reset_index()
        )

    # Write workbook (Pandas 3.0 requires keyword-only)
    with pd.ExcelWriter(outfile, engine="openpyxl") as xw:
        apps_df.to_excel(excel_writer=xw, sheet_name="Input_Data", index=False)
        df_svc.to_excel(excel_writer=xw, sheet_name=f"{provider}_Services", index=False)
        df_cost.to_excel(excel_writer=xw, sheet_name="Costing", index=False)
        df_rat.to_excel(excel_writer=xw, sheet_name="Rationale", index=False)
        df_p_app.to_excel(excel_writer=xw, sheet_name="Pivot_Cost_by_App", index=False)
        df_p_rp.to_excel(excel_writer=xw, sheet_name="Pivot_Cost_by_RPattern", index=False)
        df_p_env.to_excel(excel_writer=xw, sheet_name="Pivot_Cost_by_Environment", index=False)

    log(f"[OK] Wrote: {outfile}")


# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------
def main():
    reset_log()
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=os.path.join(SCRIPT_DIR, "input_apps.csv"))
    ap.add_argument("--pricing", choices=["industry","standard"], default="industry")
    ap.add_argument("--rate_model",
                    choices=["payg","ri_1yr","ri_3yr","sp_1yr","sp_3yr"],
                    default="payg")
    args = ap.parse_args()

    apps_df = read_apps(args.input)

    az  = load_pricing("Azure", args.pricing)
    aws = load_pricing("AWS",   args.pricing)
    gcp = load_pricing("GCP",   args.pricing)

    build_workbook(apps_df, "Azure", az, args.rate_model, args.pricing, args.input)
    build_workbook(apps_df, "AWS",   aws, args.rate_model, args.pricing, args.input)
    build_workbook(apps_df, "GCP",   gcp, args.rate_model, args.pricing, args.input)

    log("PROCESS COMPLETE.")


if __name__=="__main__":
    main()