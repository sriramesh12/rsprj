#!/usr/bin/env python3
"""
generate_price_models.py  (FINAL — Option B)

This generator produces two pricing models for Azure, AWS, and GCP:
    • industry_prices.json
    • standard_prices.json

It ensures COMPUTE pricing for ALL clouds uses a FLAT LADDER structure:
    compute.vm.<size> = {
        "payg": <float>,
        "ri_1yr": <float>,
        "ri_3yr": <float>,
        "sp_1yr": <float>,
        "sp_3yr": <float>
    }

This matches real cloud pricing, where AWS Savings Plans and Azure Savings Plans/Reservations
publish *distinct* per-term discounted rates relative to PAYG
(up to 72% savings for AWS 3‑year commitments, per AWS docs)  [1](https://pandas.pydata.org/docs/dev/whatsnew/v3.0.0.html)
(and Azure’s 1/3‑year reservation pricing model)  [2](https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.ExcelWriter.html)

Output is consumed by v4_compute_storage_only.py and v5_full_migration_costing.py.
"""

import json, os, argparse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PRICING_DIR = os.path.join(SCRIPT_DIR, "cloud-pricing")
os.makedirs(PRICING_DIR, exist_ok=True)

# -----------------------------------------------------------
#  Discount multipliers for RI/SP (industry defaults)
#  If standard mode is requested, we override with actual discounted prices.
# -----------------------------------------------------------
RI_1YR_DISC = 0.70     # approx typical discount vs PAYG
RI_3YR_DISC = 0.50
SP_1YR_DISC = 0.70
SP_3YR_DISC = 0.55

# -----------------------------------------------------------
#  Helper: flatten or ladderize compute.vm & node-hour objects
# -----------------------------------------------------------
def flatten_compute_vm(vm_dict):
    """
    Ensures compute.vm.<instance> is flattened to:
        { payg, ri_1yr, ri_3yr, sp_1yr, sp_3yr }
    regardless of whether input was:
        { "payg": <num> }
        { "payg": { ladder } }
        <num>
    """
    out = {}
    for inst, val in vm_dict.items():

        # Case A — bare number (industry simple models)
        if isinstance(val, (int, float)):
            base = {"payg": val}

        # Case B — industry: {"payg": number}
        elif isinstance(val, dict) and isinstance(val.get("payg"), (int, float)):
            base = {"payg": val["payg"]}

        # Case C — standard old-style: {"payg": { ladder }}
        elif isinstance(val, dict) and isinstance(val.get("payg"), dict):
            base = val["payg"]

        # Case D — already flattened
        else:
            base = val

        payg = base.get("payg", 0.0)

        out[inst] = {
            "payg": payg,
            "ri_1yr":  base.get("ri_1yr", round(payg * RI_1YR_DISC, 4)),
            "ri_3yr":  base.get("ri_3yr", round(payg * RI_3YR_DISC, 4)),
            "sp_1yr":  base.get("sp_1yr", round(payg * SP_1YR_DISC, 4)),
            "sp_3yr":  base.get("sp_3yr", round(payg * SP_3YR_DISC, 4))
        }
    return out


def flatten_node_hour(node_dict):
    """
    ECS/GKE/AKS node rates:
        "m5.large": <num>  OR
        "m5.large": { ladder }
        "m5.large": { "payg": <num> }
    → always flatten to full ladder
    """
    out = {}
    for size, val in node_dict.items():

        if isinstance(val, (int, float)):
            base = {"payg": val}
        elif isinstance(val, dict) and isinstance(val.get("payg"), (int, float)):
            base = {"payg": val["payg"]}
        elif isinstance(val, dict):
            base = val
        else:
            base = {"payg": 0.0}

        payg = base.get("payg", 0.0)
        out[size] = {
            "payg": payg,
            "ri_1yr": base.get("ri_1yr", round(payg * RI_1YR_DISC, 4)),
            "ri_3yr": base.get("ri_3yr", round(payg * RI_3YR_DISC, 4)),
            "sp_1yr": base.get("sp_1yr", round(payg * SP_1YR_DISC, 4)),
            "sp_3yr": base.get("sp_3yr", round(payg * SP_3YR_DISC, 4))
        }

    return out

# -----------------------------------------------------------
#  Build cloud baseline models before flattening
# -----------------------------------------------------------
def build_azure_base():
    return {
        "meta": {
            "provider": "Azure",
            "region": "East US",
            "env_discounts": {
                "Prod": 0.70,      # industry
                "Non-Prod": 0.85
            }
        },
        "compute": {
            "vm": {
                "D2s_v5": 0.096,
                "D4s_v5": 0.192,
                "D8s_v5": 0.384,
                "B2ms":   0.046,
                "F4s_v2": 0.169,
            },
            "appservice_hour": {
                "P1v3": 0.51,
                "S1":   0.3125
            },
            "aks_node_hour": {
                "D2s_v5": 0.096,
                "D4s_v5": 0.192,
                "D8s_v5": 0.384,
                "B2ms":   0.046,
                "F4s_v2": 0.169
            }
        },
        "storage": {
            "blob_hot_gb_month": 0.018,
            "files_gb_month":    0.06
        },
        "database": {
            "azure_sql_hour": {
                "GP_vcore8": 0.504,
                "GP_vcore2": 0.126
            }
        },
        "networking": {
            "app_gateway_waf_month": {
                "prod":   355.73,
                "nonprod":323.39
            },
            "lb_basic_month": {
                "month": 18.25
            }
        },
        "integration": {
            "apim_month": {
                "prod":   985.0,
                "nonprod":299.0
            }
        },
        "monitoring": {
            "log_analytics_ingest_gb": 0.10,
            "ingest_gb_day": {
                "prod": 5,
                "nonprod": 1
            }
        },
        "security": {
            "key_vault_month": {
                "prod":   4.00,
                "nonprod":2.00
            },
            "firewall_month": {
                "prod":   995.00,
                "nonprod":650.00
            }
        },
        "os": {
            "windows_hour": 0.046,
            "rhel_hour":    0.06,
            "suse_hour":    0.04
        }
    }


def build_aws_base():
    return {
        "meta": {
            "provider": "AWS",
            "region": "us-east-1",
            "env_discounts": {
                "Prod": 0.70,
                "Non-Prod": 0.85
            }
        },
        "compute": {
            "vm": {
                "m5.large": 0.096,
                "m5.xlarge":0.192,
                "m5.2xlarge":0.384,
                "t3.medium":0.0416,
                "c5.large":0.085
            },
            "ecs_node_hour": {
                "m5.large": 0.096,
                "m5.xlarge":0.192,
                "m5.2xlarge":0.384,
                "t3.medium":0.0416,
                "c5.large":0.085
            },
            "lambda_gb_second": 1.67e-5
        },
        "storage": {
            "s3_standard_gb_month":0.023,
            "ebs_gp3_gb_month":    0.08
        },
        "database": {
            "rds_hour": {
                "db_m5_large": 0.29
            }
        },
        "networking": {
            "alb_hour":      0.0225,
            "alb_lcu_hour":  0.008,
            "nat_gateway_hour": 0.045,
            "nat_data_gb":      0.045
        },
        "integration": {
            "api_gateway_month_small": 21.0,
            "sqs_million_ops":         0.40
        },
        "monitoring": {
            "cloudwatch_log_ingest_gb": 0.50,
            "ingest_gb_day": {
                "prod": 5,
                "nonprod": 1
            }
        },
        "security": {
            "secrets_manager_month": 0.40,
            "kms_month": 1.00,
            "network_firewall_data_gb": 0.065
        },
        "cdn_dns": {
            "cloudfront_egress_gb":0.085,
            "route53_zone_month": 0.50
        },
        "os": {
            "windows_hour": 0.046,
            "rhel_hour":    0.06,
            "suse_hour":    0.04
        }
    }


def build_gcp_base():
    return {
        "meta": {
            "provider": "GCP",
            "region": "us-central1",
            "env_discounts": {
                "Prod": 0.70,
                "Non-Prod": 0.85
            }
        },
        "compute": {
            "vm": {
                "n2-standard-2": 0.095,
                "n2-standard-4": 0.19,
                "e2-standard-2": 0.067,
                "e2-standard-4": 0.134,
                "c2-standard-4": 0.21
            },
            "gke_node_hour": {
                "n2-standard-2": 0.095,
                "n2-standard-4": 0.19,
                "e2-standard-2": 0.067,
                "e2-standard-4": 0.134,
                "c2-standard-4": 0.21
            },
            "cloud_run_hour": 0.10,
            "cloudfunctions_gb_second":1.6e-5
        },
        "storage": {
            "gcs_standard_gb_month": 0.020,
            "pd_ssd_gb_month": 0.17
        },
        "database": {
            "cloudsql_hour_small": 0.095
        },
        "networking": {
            "glb_hour": 0.025,
            "cloud_nat_hour":0.045,
            "cloud_nat_data_gb":0.045
        },
        "integration": {
            "api_gateway_month_small":21.0
        },
        "monitoring": {
            "logging_ingest_gb":0.50,
            "ingest_gb_day":{
                "prod":5,
                "nonprod":1
            }
        },
        "security": {
            "secret_manager_month":0.40,
            "kms_month":1.00,
            "cloud_armor_hour":0.075
        },
        "cdn_dns":{
            "cloud_cdn_egress_gb":0.085,
            "cloud_dns_zone_month":0.50
        },
        "os":{
            "windows_hour":0.046,
            "rhel_hour":0.06,
            "suse_hour":0.04
        }
    }


# -----------------------------------------------------------
#  Generate industry or standard pricing
# -----------------------------------------------------------
def build_prices(mode):
    if mode not in ("industry","standard"):
        raise ValueError("mode must be 'industry' or 'standard'")

    azure = build_azure_base()
    aws   = build_aws_base()
    gcp   = build_gcp_base()

    clouds = {"Azure": azure, "AWS": aws, "GCP": gcp}

    for name, model in clouds.items():
        # Flatten compute.vm
        model["compute"]["vm"] = flatten_compute_vm(model["compute"]["vm"])

        # Flatten node runtimes
        if "aks_node_hour" in model["compute"]:
            model["compute"]["aks_node_hour"] = flatten_node_hour(model["compute"]["aks_node_hour"])
        if "ecs_node_hour" in model["compute"]:
            model["compute"]["ecs_node_hour"] = flatten_node_hour(model["compute"]["ecs_node_hour"])
        if "gke_node_hour" in model["compute"]:
            model["compute"]["gke_node_hour"] = flatten_node_hour(model["compute"]["gke_node_hour"])

        # For STANDARD: keep explicit ladders
        # For INDUSTRY: keep single PAYG plus env discounts (scripts apply env_disc)
        if mode == "industry":
            # Industry wipes out ladders, keeps PAYG only
            for inst, obj in model["compute"]["vm"].items():
                payg = obj["payg"]
                model["compute"]["vm"][inst] = {"payg": payg}

            for section in ("aks_node_hour","ecs_node_hour","gke_node_hour"):
                if section in model["compute"]:
                    nd = model["compute"][section]
                    for size, obj in nd.items():
                        nd[size] = {"payg": obj["payg"]}

        # Done – now produce uniform, stable pricing JSON
    return clouds


# -----------------------------------------------------------
#  Main entry point
# -----------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["industry","standard"], default="standard")
    args = ap.parse_args()

    clouds = build_prices(args.mode)

    for provider, data in clouds.items():
        fn = f"{provider.lower()}_prices_{args.mode}.json"
        path = os.path.join(PRICING_DIR, fn)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        print(f"Wrote: {path}")


if __name__ == "__main__":
    main()