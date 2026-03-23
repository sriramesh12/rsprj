"""
Streamlit web interface for Cloud Rationalization Agent
Complete fixed version - No 60s wait on errors, agent persists, auto-initializes
"""
import sys
import os
from pathlib import Path
import matplotlib.pyplot as plt
import io
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
import tempfile

# Add the project root to Python path
project_root = str(Path(__file__).parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Import helpers with fallbacks for missing functions
try:
    from src.utils.helpers import apply_ssl_fix, format_currency, safe_serialize
    apply_ssl_fix()
    HELPERS_AVAILABLE = True
except ImportError:
    HELPERS_AVAILABLE = False
    # Define fallback functions
    def format_currency(amount, currency="USD"):
        return f"${amount:,.2f}" if amount else "$0.00"
    def safe_serialize(obj):
        if hasattr(obj, 'dict'):
            return obj.dict()
        return obj

# Now try the main imports
try:
    from src.agent import CloudRationalizationAgent
    from src.models.schemas import (
        RationalizationRequest, 
        CloudResource,
        BusinessConstraints,
        CloudProvider,
        ResourceType,
        UsagePattern,
        OptimizationGoal
    )
    print("✅ Imports successful")
except ImportError as e:
    print(f"❌ Import error: {e}")
    print(f"Current sys.path: {sys.path}")

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import asyncio
import json
from datetime import datetime
import requests
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ===== PAGE CONFIGURATION =====
st.set_page_config(
    page_title="Cloud Rationalization Agent",
    page_icon="☁️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ===== HELPER FUNCTIONS - DEFINED FIRST =====

# ===== HELPER FUNCTIONS FOR MIGRATION ANALYSIS ===== tab5

# ===== MIGRATION REPORTING FUNCTIONS =====

def create_migration_distribution_chart(strategy_counts):
    """Create a pie chart showing strategy distribution"""
    fig, ax = plt.subplots(figsize=(8, 6))
    
    strategies = list(strategy_counts.keys())
    counts = list(strategy_counts.values())
    colors_list = ['#4CAF50', '#2196F3', '#FF9800', '#F44336', '#9C27B0']
    
    # Filter out zero counts
    non_zero = [(s, c) for s, c in zip(strategies, counts) if c > 0]
    if non_zero:
        strategies, counts = zip(*non_zero)
    
    wedges, texts, autotexts = ax.pie(
        counts, 
        labels=strategies, 
        autopct='%1.1f%%',
        colors=colors_list[:len(counts)],
        startangle=90
    )
    
    ax.set_title('Migration Strategy Distribution', fontsize=16, pad=20)
    plt.setp(autotexts, size=10, weight="bold", color="white")
    plt.setp(texts, size=11)
    
    return fig

def create_timeline_feasibility_chart(timeline_summary):
    """Create a bar chart showing timeline feasibility"""
    fig, ax = plt.subplots(figsize=(8, 4))
    
    categories = ['Feasible', 'Challenging', 'Not Feasible']
    counts = [
        timeline_summary.get('feasible_count', 0),
        timeline_summary.get('challenging_count', 0),
        timeline_summary.get('not_feasible_count', 0)
    ]
    colors = ['#4CAF50', '#FFC107', '#F44336']
    
    bars = ax.bar(categories, counts, color=colors)
    ax.set_title('Migration Timeline Feasibility', fontsize=14, pad=10)
    ax.set_ylabel('Number of Servers')
    ax.grid(axis='y', alpha=0.3)
    
    # Add value labels on bars
    for bar, count in zip(bars, counts):
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height,
                f'{count}', ha='center', va='bottom', fontsize=11)
    
    return fig

def create_cost_comparison_chart(cloud_cost, total_servers):
    """Create a bar chart showing on-prem vs cloud costs (cloud should be cheaper)"""
    fig, ax = plt.subplots(figsize=(8, 5))
    
    # Calculate on-prem cost (typically 30-40% higher than cloud)
    # Using a more realistic multiplier based on industry averages
    on_prem_multiplier = 1.4  # On-prem is 40% more expensive
    on_prem_cost = cloud_cost * on_prem_multiplier
    
    # Calculate savings
    monthly_savings = on_prem_cost - cloud_cost
    annual_savings = monthly_savings * 12
    
    categories = ['On-Premise (Estimated)', f'Cloud ({target_cloud})']
    costs = [on_prem_cost, cloud_cost]
    colors = ['#FF9800', '#4CAF50']  # Orange for on-prem, Green for cloud
    
    bars = ax.bar(categories, costs, color=colors)
    ax.set_title('Cost Comparison: On-Premise vs Cloud', fontsize=14, pad=10)
    ax.set_ylabel('Monthly Cost ($)')
    ax.grid(axis='y', alpha=0.3)
    
    # Format y-axis with dollar values
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x:,.0f}'))
    
    # Add value labels on bars
    for bar, cost in zip(bars, costs):
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height,
                f'${cost:,.0f}', ha='center', va='bottom', fontsize=11)
    
    # Add savings annotation
    ax.text(0.5, 0.95, f'💰 Monthly Savings: ${monthly_savings:,.0f}',
            transform=ax.transAxes, ha='center', fontsize=12,
            bbox=dict(boxstyle='round', facecolor='#4CAF20', alpha=0.3))
    
    return fig, monthly_savings, annual_savings

def generate_migration_pdf_report(analysis, target_cloud, migration_priority, migration_timeline, 
                                 compliance_req, include_charts):
    """Generate a PDF report for migration analysis - WITH GRAPHS"""
    
    # Create a temporary file for the PDF
    with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
        pdf_file = tmp.name
    
    try:
        # Create PDF document
        from reportlab.lib.pagesizes import letter
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib import colors
        from reportlab.lib.units import inch
        import matplotlib.pyplot as plt
        import io
        
        doc = SimpleDocTemplate(pdf_file, pagesize=letter)
        styles = getSampleStyleSheet()
        story = []
        
        # Custom styles
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=18,
            textColor=colors.HexColor('#1E88E5'),
            spaceAfter=12,
            alignment=1
        )
        
        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontSize=14,
            textColor=colors.HexColor('#333333'),
            spaceAfter=8,
            spaceBefore=12
        )
        
        normal_style = styles['Normal']
        
        # Title
        story.append(Paragraph("Cloud Migration Strategy Report", title_style))
        story.append(Spacer(1, 0.2*inch))
        
        # Date
        from datetime import datetime
        date_str = datetime.now().strftime("%B %d, %Y")
        story.append(Paragraph(f"Generated: {date_str}", normal_style))
        story.append(Spacer(1, 0.2*inch))
        
        # Calculate savings
        cloud_cost = analysis['summary']['estimated_monthly_cost']
        on_prem_cost = cloud_cost * 1.4
        monthly_savings = on_prem_cost - cloud_cost
        annual_savings = monthly_savings * 12
        savings_percentage = ((on_prem_cost - cloud_cost) / on_prem_cost * 100)
        
        # Executive Summary
        story.append(Paragraph("Executive Summary", heading_style))
        
        summary_text = f"""
        This report provides a comprehensive migration strategy for {analysis['summary']['total_servers']} on-premise servers to {target_cloud}. 
        Based on the migration priority '{migration_priority}', timeline '{migration_timeline}'.
        """
        story.append(Paragraph(summary_text, normal_style))
        story.append(Spacer(1, 0.1*inch))
        
        # Financial Benefits
        story.append(Paragraph("Financial Benefits", heading_style))
        story.append(Paragraph(f"• Estimated Monthly Cloud Cost: ${cloud_cost:,.0f}", normal_style))
        story.append(Paragraph(f"• Estimated On-Premise Cost: ${on_prem_cost:,.0f}", normal_style))
        story.append(Paragraph(f"• Monthly Savings: ${monthly_savings:,.0f} ({savings_percentage:.0f}%)", normal_style))
        story.append(Paragraph(f"• Annual Savings: ${annual_savings:,.0f}", normal_style))
        story.append(Spacer(1, 0.2*inch))
        
   
        # Key Metrics Table
        story.append(Paragraph("Key Metrics", heading_style))
        
        metrics_data = [
            ["Metric", "Value"],
            ["Total Servers", str(analysis['summary']['total_servers'])],
            ["Target Cloud", target_cloud],
            ["Migration Priority", migration_priority],
            ["Migration Timeline", migration_timeline],
            ["Primary Strategy", analysis['summary']['primary_strategy']],
            ["Cloud Cost (Monthly)", f"${cloud_cost:,.0f}"],
            ["On-Prem Cost (Monthly)", f"${on_prem_cost:,.0f}"],
            ["Monthly Savings", f"${monthly_savings:,.0f}"]
        ]
        
        metrics_table = Table(metrics_data, colWidths=[2.5*inch, 2.5*inch])
        metrics_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (1, 0), colors.HexColor('#1E88E5')),
            ('TEXTCOLOR', (0, 0), (1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey)
        ]))
        story.append(metrics_table)
        story.append(Spacer(1, 0.2*inch))
        
        # Strategy Distribution Table
        story.append(Paragraph("Migration Strategy Distribution", heading_style))
        
        strategy_data = [["Strategy", "Count", "Percentage"]]
        total = analysis['summary']['total_servers']
        for strategy, count in analysis['summary']['strategy_breakdown'].items():
            if count > 0:
                percentage = (count / total) * 100
                strategy_data.append([strategy, str(count), f"{percentage:.1f}%"])
        
        strategy_table = Table(strategy_data, colWidths=[2*inch, 1*inch, 1.5*inch])
        strategy_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1E88E5')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, 0), 11),
            ('FONTSIZE', (0, 1), (-1, -1), 10),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey)
        ]))
        story.append(strategy_table)
        story.append(Spacer(1, 0.2*inch))
        
        # Detailed Recommendations (Top 5)
        story.append(Paragraph("Top 5 Server Recommendations", heading_style))
        
        for i, rec in enumerate(analysis['recommendations'][:5], 1):
            story.append(Paragraph(f"{i}. {rec['server_name']} ({rec['application_name']})", 
                                   ParagraphStyle('Bold', parent=styles['Normal'], 
                                                fontName='Helvetica-Bold', fontSize=11)))
            
            details = [
                f"• Strategy: {rec['migration_strategy']}",
                f"• Target: {rec['cloud_provider']} - {rec['cloud_instance']}",
                f"• Monthly Cost: ${rec['monthly_cost']:,.2f}",
                f"• Confidence: {rec['confidence']}%",
                f"• Rationale: {rec['rationale']}"
            ]
            
            for detail in details:
                story.append(Paragraph(detail, normal_style))
            story.append(Spacer(1, 0.1*inch))
        
        # Build PDF
        doc.build(story)
        
        return pdf_file
        
    except Exception as e:
        st.error(f"PDF generation failed: {e}")
        import traceback
        traceback.print_exc()
        return None

def determine_strategy(application, preference):
    """
    Strategy determined by: 70% application, 30% preference
    """
    
    # STAGE 1: Base scores from application characteristics
    base_scores = calculate_base_scores(application)
    # e.g., {"Rehost": 50, "Replatform": 70, "Refactor": 30, ...}
    
    # STAGE 2: Apply preference multipliers
    preference_multipliers = get_preference_multipliers(preference)
    # e.g., {"Rehost": 1.2, "Replatform": 1.0, "Refactor": 0.8}
    
    final_scores = {}
    for strategy, base_score in base_scores.items():
        multiplier = preference_multipliers.get(strategy, 1.0)
        final_scores[strategy] = base_score * multiplier
    
    # Choose strategy with highest final score
    strategy = max(final_scores, key=final_scores.get)
    
    # The SUMMARY shows the actual strategies chosen
    # NOT just preference-based counts


def _find_column_index_fixed(df, possible_names):
    """Find column index for required columns (exact match)"""
    for i, col in enumerate(df.columns):
        col_lower = str(col).lower().strip()
        for name in possible_names:
            if name.lower() in col_lower or col_lower in name.lower():
                return i
    return 0

def _find_column_index_with_na(df, possible_names):
    """Find column index for optional columns (+1 for 'Not in file')"""
    for i, col in enumerate(df.columns):
        col_lower = str(col).lower().strip()
        for name in possible_names:
            if name.lower() in col_lower or col_lower in name.lower():
                return i + 1  # +1 because 'Not in file' is at index 0
    return 0  # 'Not in file' (index 0)

def analyze_onprem_migration_tool(onprem_resources, target_cloud, migration_priority, compliance_req, migration_timeline):
    """
    Tool-based on-prem to cloud migration analysis with 5 R's
    Now includes migration timeline and compliance requirements
    """
    
    recommendations = []
    total_cost = 0
    strategy_counts = {"Rehost": 0, "Replatform": 0, "Refactor": 0, "Retire": 0, "Retain": 0}
    
    # ===== TIMELINE IMPACT =====
    timeline_impact = {
        "Immediate (<3 months)": {
            "Rehost": 1.4,        # Fastest option
            "Replatform": 0.8,     # Takes time to replatform
            "Refactor": 0.3,       # Too slow for immediate
            "Retire": 1.2,
            "Retain": 1.1
        },
        "3-6 months": {
            "Rehost": 1.2,
            "Replatform": 1.1,
            "Refactor": 0.7,
            "Retire": 1.1,
            "Retain": 0.9
        },
        "6-12 months": {
            "Rehost": 0.9,
            "Replatform": 1.2,
            "Refactor": 1.1,
            "Retire": 1.0,
            "Retain": 0.7
        },
        "12+ months": {
            "Rehost": 0.7,
            "Replatform": 1.3,
            "Refactor": 1.4,      # Enough time to refactor
            "Retire": 1.0,
            "Retain": 0.5
        },
        "Planning Phase": {
            "Rehost": 0.8,
            "Replatform": 1.1,
            "Refactor": 1.2,       # Planning phase is good for refactor
            "Retire": 1.0,
            "Retain": 1.0
        }
    }
    
    # ===== COMPLIANCE REQUIREMENTS =====
    # Different compliance requirements affect strategy scores
    compliance_impact = {
        "SOC2": {
            "Replatform": 1.2,     # Managed services often SOC2 compliant
            "Refactor": 1.1,
            "Retain": 0.8
        },
        "HIPAA": {
            "Replatform": 1.3,      # Cloud providers have HIPAA offerings
            "Refactor": 1.2,
            "Retain": 1.1,          # May need to retain some PHI on-prem
            "Rehost": 0.8
        },
        "GDPR": {
            "Replatform": 1.2,
            "Refactor": 1.1,
            "Retain": 1.0
        },
        "PCI-DSS": {
            "Replatform": 1.3,      # Cloud has PCI compliant services
            "Refactor": 1.2,
            "Retain": 0.9
        },
        "ISO27001": {
            "Replatform": 1.1,
            "Refactor": 1.1,
            "Retain": 0.9
        }
    }
    
    # Get timeline multipliers
    timeline_multipliers = timeline_impact.get(migration_timeline, timeline_impact["3-6 months"])
    
    # Combine compliance multipliers
    compliance_multipliers = {}
    for req in compliance_req:
        if req in compliance_impact and req != "None":
            for strategy, mult in compliance_impact[req].items():
                compliance_multipliers[strategy] = compliance_multipliers.get(strategy, 1.0) * mult
    
    # Preference multipliers (existing)
    preference_multipliers = {
        "Cost Optimization": {
            "Rehost": 1.3, "Replatform": 1.1, "Refactor": 0.7, "Retire": 1.2, "Retain": 0.5
        },
        "Performance": {
            "Rehost": 0.8, "Replatform": 1.2, "Refactor": 1.3, "Retire": 1.0, "Retain": 0.6
        },
        "Lift & Shift": {
            "Rehost": 1.5, "Replatform": 0.5, "Refactor": 0.3, "Retire": 1.0, "Retain": 0.8
        },
        "Modernize": {
            "Rehost": 0.4, "Replatform": 1.3, "Refactor": 1.5, "Retire": 1.0, "Retain": 0.5
        }
    }
    
    priority_multipliers = preference_multipliers.get(migration_priority, preference_multipliers["Cost Optimization"])
    
    for r in onprem_resources:
        # ===== STAGE 1: Calculate BASE scores from application =====
        base_scores = calculate_base_scores(r, compliance_req)
        
        # ===== STAGE 2: Apply ALL multipliers =====
        preference_weight = 0.3
        application_weight = 0.7
        final_scores = {}
        for strategy, base_score in base_scores.items():
            # Start with base score
            #score = base_score
            
            # Apply priority multiplier
            #score *= priority_multipliers.get(strategy, 1.0)
            
            # Apply timeline multiplier
            #score *= timeline_multipliers.get(strategy, 1.0)
            
            # Apply compliance multiplier
            #score *= compliance_multipliers.get(strategy, 1.0)
            # Application-driven base score (70% weight)
            app_component = base_score * application_weight
            
            # Preference multiplier effect (30% weight)
            pref_mult = priority_multipliers.get(strategy, 1.0)
            pref_component = 50 * preference_weight * (pref_mult - 0.5)  # Normalize multiplier effect
            
            # Timeline impact (additional factor)
            time_mult = timeline_multipliers.get(strategy, 1.0)
            time_component = 20 * (time_mult - 0.8) if time_mult != 1.0 else 0
            
            # Compliance impact
            comp_mult = compliance_multipliers.get(strategy, 1.0)
            comp_component = 20 * (comp_mult - 0.9) if comp_mult != 1.0 else 0
            
            #final_scores[strategy] = app_component + pref_component + time_component + comp_component
            score = app_component + pref_component + time_component + comp_component
            
            # Special compliance handling for sensitive data
            data_sensitivity = r.get('data_sensitivity', 'internal')
            if data_sensitivity in ['pii', 'financial', 'hipaa']:
                if 'HIPAA' in compliance_req and strategy == "Replatform":
                    score *= 1.2  # Extra boost for replatform with HIPAA
                elif 'PCI-DSS' in compliance_req and strategy == "Replatform":
                    score *= 1.15
            
            final_scores[strategy] = score
        
        # Choose strategy with highest final score
        strategy = max(final_scores, key=final_scores.get)
        confidence = final_scores[strategy]
        
        # Generate rationale that includes timeline and compliance
        rationale = generate_enhanced_rationale(
            r, strategy, migration_priority, migration_timeline, 
            compliance_req, base_scores, priority_multipliers,
            timeline_multipliers, compliance_multipliers
        )
        
        # Calculate cost
        monthly_cost = estimate_cloud_cost_by_specs(r, target_cloud, strategy)
        total_cost += monthly_cost
        strategy_counts[strategy] = strategy_counts.get(strategy, 0) + 1
        
        recommendations.append({
            "server_name": r.get('server_name', 'Unknown'),
            "application_name": r.get('application_name', 'Unknown'),
            "migration_strategy": strategy,
            "cloud_provider": target_cloud if target_cloud != "Multi-Cloud (All)" else "Multi-Cloud",
            "cloud_instance": get_instance_by_specs(r, target_cloud),
            "monthly_cost": round(monthly_cost, 2),
            "confidence": round(min(confidence, 100), 1),  # Cap at 100
            "migration_effort": get_effort_by_strategy(strategy),
            "rationale": rationale,
            "timeline_feasibility": get_timeline_feasibility(strategy, migration_timeline),
            "compliance_ready": check_compliance_readiness(strategy, compliance_req, r),
            "next_steps": get_next_steps_by_strategy(strategy,target_cloud,r)
        })
    
    # Determine primary strategy
    primary_strategy = max(strategy_counts, key=strategy_counts.get)
    
    # Calculate timeline feasibility summary
    timeline_summary = analyze_timeline_feasibility(recommendations, migration_timeline)
    
    return {
        "summary": {
            "total_servers": len(onprem_resources),
            "estimated_monthly_cost": round(total_cost, 2),
            "primary_strategy": primary_strategy,
            "strategy_breakdown": strategy_counts,
            "migration_priority_used": migration_priority,
            "timeline_used": migration_timeline,
            "compliance_requirements": compliance_req,
            "timeline_feasibility": timeline_summary
        },
        "recommendations": recommendations
    }



def calculate_base_scores(resource, compliance_req):
    """Calculate base scores based on application characteristics only"""
    
    scores = {"Rehost": 50, "Replatform": 50, "Refactor": 50, "Retire": 20, "Retain": 20}
    
    # Extract characteristics
    app_tier = resource.get('app_tier', '').lower()
    workload = resource.get('workload_type', '').lower()
    db_type = resource.get('database_type', '').lower()
    os_type = resource.get('os', '').lower()
    middleware = resource.get('middleware', '').lower()
    criticality = resource.get('business_criticality', 'medium').lower()
    sensitivity = resource.get('data_sensitivity', 'internal').lower()
    age = int(resource.get('age_years', 3))
    end_of_life = resource.get('end_of_life', False)
    fault_tolerant = resource.get('fault_tolerant', False)
    cpu_util = float(resource.get('cpu_utilization', 30))
    
    # ===== DATABASE TIER =====
    if 'database' in workload or 'data' in app_tier or db_type:
        scores["Replatform"] += 30
        if 'sql server' in db_type or 'oracle' in db_type:
            scores["Rehost"] += 10
            scores["Refactor"] -= 20
        elif 'postgres' in db_type or 'mysql' in db_type:
            scores["Replatform"] += 20
            scores["Refactor"] += 10
        elif 'mongodb' in db_type or 'nosql' in db_type:
            scores["Refactor"] += 40
            scores["Replatform"] += 10
    
    # ===== WEB/APP TIER =====
    elif 'web' in app_tier or 'app' in app_tier:
        scores["Rehost"] += 15
        if 'windows' in os_type and ('.net' in middleware or 'iis' in middleware):
            scores["Replatform"] += 25
            scores["Refactor"] += 10
        elif 'java' in middleware:
            scores["Refactor"] += 20
            scores["Replatform"] += 15
        else:
            scores["Rehost"] += 20
    
    # ===== BATCH/ETL =====
    elif 'batch' in workload or 'etl' in workload:
        if fault_tolerant:
            scores["Replatform"] += 25
            scores["Refactor"] += 20
        else:
            scores["Rehost"] += 25
    
    # ===== AGE/RETIREMENT =====
    if age > 7 or end_of_life:
        scores["Retire"] += 40
        scores["Rehost"] -= 20
        scores["Refactor"] -= 30
    
    # ===== CRITICALITY =====
    if criticality == 'high':
        scores["Retain"] += 25
        scores["Refactor"] -= 20
        scores["Rehost"] += 10
    
    # ===== COMPLIANCE =====
    if sensitivity in ['pii', 'financial', 'hipaa', 'gdpr']:
        if 'hipaa' in compliance_req or 'pci' in compliance_req:
            scores["Retain"] += 40
        else:
            scores["Replatform"] += 15  # Managed services often have compliance
    
    # ===== UTILIZATION =====
    if cpu_util < 20:
        scores["Rehost"] -= 10  # Over-provisioned
        scores["Refactor"] += 15  # Right-size opportunity
    
    return scores

def generate_rationale(resource, strategy, priority, base_scores, multipliers):
    """Generate explanation that includes both factors"""
    
    server = resource.get('server_name', 'Unknown')
    app = resource.get('application_name', 'Unknown')
    workload = resource.get('workload_type', 'Unknown')
    
    base = base_scores[strategy]
    multiplier = multipliers.get(strategy, 1.0)
    
    if strategy == "Rehost":
        return f"{server} ({app}) - Rehost recommended because: " + \
               f"Workload '{workload}' is well-suited for lift & shift. " + \
               f"Base suitability: {base:.0f}/100, " + \
               f"Preference for {priority} further supports this strategy (x{multiplier})."
    
    elif strategy == "Replatform":
        return f"{server} ({app}) - Replatform to managed services because: " + \
               f"Workload '{workload}' can benefit from cloud-managed infrastructure. " + \
               f"Base suitability: {base:.0f}/100, " + \
               f"Your {priority} priority aligns with this approach (x{multiplier})."
    
    elif strategy == "Refactor":
        return f"{server} ({app}) - Refactor to cloud-native because: " + \
               f"Workload '{workload}' is a good candidate for modernization. " + \
               f"Base suitability: {base:.0f}/100, " + \
               f"Your {priority} priority strongly encourages this transformation (x{multiplier})."
    
    elif strategy == "Retire":
        return f"{server} ({app}) - Consider retirement: Server age and utilization suggest evaluation for decommissioning."
    
    else:  # Retain
        return f"{server} ({app}) - Retain on-premises due to compliance or criticality requirements."

def get_timeline_feasibility(strategy, timeline):
    """Determine if strategy is feasible within timeline"""
    feasibility = {
        "Immediate (<3 months)": {
            "Rehost": "✅ Highly Feasible",
            "Replatform": "⚠️ Challenging",
            "Refactor": "❌ Not Feasible",
            "Retire": "✅ Feasible",
            "Retain": "✅ Feasible"
        },
        "3-6 months": {
            "Rehost": "✅ Feasible",
            "Replatform": "✅ Feasible",
            "Refactor": "⚠️ Tight but possible",
            "Retire": "✅ Feasible",
            "Retain": "✅ Feasible"
        },
        "6-12 months": {
            "Rehost": "✅ Feasible",
            "Replatform": "✅ Feasible",
            "Refactor": "✅ Feasible",
            "Retire": "✅ Feasible",
            "Retain": "✅ Feasible"
        }
    }
    return feasibility.get(timeline, {}).get(strategy, "⚠️ Unknown")

def check_compliance_readiness(strategy, compliance_req, resource):
    """Check if strategy meets compliance requirements"""
    if not compliance_req or "None" in compliance_req:
        return "✅ No specific compliance requirements"
    
    data_sensitivity = resource.get('data_sensitivity', 'internal')
    
    if strategy == "Retain":
        return "✅ On-premise retention ensures compliance control"
    
    if strategy == "Replatform":
        return "⚠️ Verify cloud provider's compliance certifications"
    
    if strategy == "Refactor":
        return "⚠️ Design with compliance in mind"
    
    return "✅ Standard compliance measures apply"

def analyze_timeline_feasibility(recommendations, timeline):
    """Summarize timeline feasibility across all recommendations"""
    total = len(recommendations)
    feasible = sum(1 for r in recommendations if "✅" in r['timeline_feasibility'])
    challenging = sum(1 for r in recommendations if "⚠️" in r['timeline_feasibility'])
    not_feasible = sum(1 for r in recommendations if "❌" in r['timeline_feasibility'])
    
    return {
        "feasible_count": feasible,
        "challenging_count": challenging,
        "not_feasible_count": not_feasible,
        "overall": f"{feasible}/{total} servers can be migrated within {timeline.lower()}"
    }

def generate_enhanced_rationale(resource, strategy, priority, timeline, compliance, 
                                base_scores, priority_mult, timeline_mult, compliance_mult):
    """Generate detailed rationale - Application characteristics first, preferences second"""
    
    server = resource.get('server_name', 'Unknown')
    app = resource.get('application_name', 'Unknown')
    workload = resource.get('workload_type', 'Unknown')
    app_tier = resource.get('app_tier', '').lower()
    db_type = resource.get('database_type', '').lower()
    os_type = resource.get('os', '').lower()
    cpu = resource.get('cpu_cores', 0)
    ram = resource.get('ram_gb', 0)
    
    base = base_scores[strategy]
    
    # ===== APPLICATION CHARACTERISTICS (Primary) =====
    app_reason = ""
    
    if 'database' in workload or 'data' in app_tier or db_type:
        if 'sql server' in db_type or 'oracle' in db_type:
            app_reason = f"Database server running {db_type} - Commercial databases are well-suited for Replatform to managed services"
        elif 'postgres' in db_type or 'mysql' in db_type:
            app_reason = f"Open source database ({db_type}) - Excellent candidate for managed database services"
        elif 'mongodb' in db_type or 'nosql' in db_type:
            app_reason = f"NoSQL database ({db_type}) - Great opportunity for Refactor to cloud-native database services"
    
    elif 'web' in app_tier or 'app' in app_tier:
        if 'windows' in os_type:
            app_reason = f"Windows-based {workload} - Compatible with cloud Windows instances and PaaS options"
        elif 'linux' in os_type:
            app_reason = f"Linux-based {workload} - Highly compatible with cloud environments, multiple deployment options"
        else:
            app_reason = f"{workload} server - Standard workload with multiple cloud deployment options"
    
    elif 'batch' in workload or 'etl' in workload:
        app_reason = f"Batch/ETL workload - Can leverage cloud-native batch processing services"
    
    elif 'file' in workload or 'storage' in app_tier:
        app_reason = f"File server - Ideal for cloud object storage solutions"
    
    else:
        app_reason = f"General purpose server ({cpu} cores, {ram} GB RAM) - Multiple cloud options available"
    
    # ===== MIGRATION PREFERENCE (Secondary) =====
    pref_reason = ""
    if strategy == "Rehost":
        if priority == "Lift & Shift":
            pref_reason = f" aligns with your '{priority}' priority for quick migration"
        elif priority == "Cost Optimization":
            pref_reason = f" supports your '{priority}' goal by minimizing migration costs"
        else:
            pref_reason = f" meets your '{priority}' requirements while maintaining architecture"
    
    elif strategy == "Replatform":
        if priority == "Modernize":
            pref_reason = f" perfectly matches your '{priority}' objective"
        elif priority == "Performance":
            pref_reason = f" enhances performance as part of your '{priority}' focus"
        else:
            pref_reason = f" balances your '{priority}' needs with cloud optimization"
    
    elif strategy == "Refactor":
        if priority == "Modernize":
            pref_reason = f" fully supports your '{priority}' goal for cloud-native transformation"
        elif priority == "Performance":
            pref_reason = f" optimizes performance for your '{priority}' requirements"
        else:
            pref_reason = f" provides long-term benefits aligned with your '{priority}' strategy"
    
    # ===== COMBINE (Application first, Preference second) =====
    rationale = f"{app_reason}. {strategy} strategy"
    if pref_reason:
        rationale += f" {pref_reason}."
    
    # Add context about confidence
    confidence_level = "high" if base > 80 else "medium" if base > 60 else "moderate"
    rationale += f" Confidence in this recommendation is {confidence_level} based on workload analysis."
    
    # Add timeline context if relevant
    if timeline in ["Immediate (<3 months)", "3-6 months"] and strategy in ["Refactor", "Replatform"]:
        rationale += f" Note: The {timeline} timeline may require phased approach for this strategy."
    
    return rationale


def analyze_onprem_migration_llm(onprem_resources, target_cloud, priority, agent):
    """LLM-based on-prem to cloud migration analysis with R pattern recommendations"""
    
    # Format detailed on-prem data for LLM
    onprem_summary = []
    for r in onprem_resources:
        onprem_summary.append(f"""
SERVER: {r['name']}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Hardware Specifications:
- CPU: {r['cpu_cores']} cores (utilization: {r.get('cpu_utilization', 30)}%)
- RAM: {r['ram_gb']} GB (utilization: {r.get('memory_utilization', 40)}%)
- Storage: {r['storage_gb']} GB ({r.get('storage_type', 'HDD')}) - {r.get('storage_utilization', 50)}% used
- Network: {r.get('network_bandwidth', 'Medium')}

Software & Workload:
- Operating System: {r['os']}
- Workload Type: {r['workload_type']}
- Database: {r.get('database_type', 'None')}
- Middleware: {r.get('middleware', 'None')}
- I/O Pattern: {r.get('io_pattern', 'Balanced')}

Business Context:
- Criticality: {r.get('criticality', 'medium')}
- High Availability Required: {r.get('fault_tolerant', False)}
- Server Age: {r.get('age_years', 3)} years
- End of Life Approaching: {r.get('end_of_life', False)}

Migration Considerations:
- Application Dependencies: Unknown (assume standard for workload type)
- Data Sensitivity: Standard (assume)
- Compliance Requirements: None specified
""")
    
    prompt = f"""
You are a cloud migration expert. Analyze this on-premise infrastructure and recommend 
the best migration strategy using the 5 R's of cloud migration:

1. **Rehost (Lift & Shift)** - Move as-is with minimal changes
2. **Replatform** - Make minor cloud optimizations without changing core architecture
3. **Refactor** - Re-architect to fully leverage cloud native services
4. **Retire** - Decommission unused or obsolete applications
5. **Retain** - Keep on-premise (for compliance, latency, or dependency reasons)

ON-PREMISE INFRASTRUCTURE:
{chr(10).join(onprem_summary)}

TARGET CLOUD: {target_cloud}
MIGRATION PRIORITY: {priority}

For EACH server, provide:
1. Recommended cloud instance/service
2. Migration strategy (which of the 5 R's)
3. Confidence score (0-100%)
4. Estimated monthly cost
5. Rationale explaining WHY this strategy fits this workload
6. Migration effort (Low/Medium/High)
7. Potential challenges and mitigation

Also consider:
- Applications with databases may need re-platforming (e.g., RDS)
- Legacy apps may need rehosting (EC2)
- Modern apps could be refactored to containers/serverless
- Batch jobs could become cloud-native services
- Web servers could use auto-scaling groups + load balancers

Format as JSON with:
- summary: total servers, estimated cost, primary strategies
- recommendations: array of detailed recommendations per server
- migration_plan: phased approach based on strategies
"""
    
    # This would call your LLM agent
    # For now, returning enhanced tool-based with R patterns
    return generate_r_pattern_recommendations(onprem_resources, target_cloud, priority)

def generate_r_pattern_recommendations(onprem_resources, target_cloud, priority):
    """Generate recommendations with R patterns"""
    
    recommendations = []
    total_cost = 0
    strategy_counts = {"Rehost": 0, "Replatform": 0, "Refactor": 0, "Retire": 0, "Retain": 0}
    
    for r in onprem_resources:
        workload = r['workload_type'].lower()
        database = r.get('database_type', '').lower()
        cpu_util = r.get('cpu_utilization', 30)
        age = r.get('age_years', 3)
        fault_tolerant = r.get('fault_tolerant', False)
        
        # Determine R pattern based on workload characteristics
        if "database" in workload or database:
            if "sql" in database or "oracle" in database:
                strategy = "Replatform"
                instance = "RDS for SQL Server/Oracle"
                rationale = f"Database workload - replatform to managed {target_cloud} RDS for better performance and reduced management overhead"
                effort = "Medium"
                confidence = 85
            elif "nosql" in database or "mongo" in database:
                strategy = "Refactor"
                instance = f"{target_cloud} DocumentDB/DynamoDB equivalent"
                rationale = "NoSQL database - opportunity to refactor to cloud-native managed service"
                effort = "High"
                confidence = 75
            else:
                strategy = "Rehost"
                instance = get_instance_by_specs(r, target_cloud)
                rationale = "Database workload - rehost initially, consider managed services later"
                effort = "Medium"
                confidence = 90
        
        elif "web" in workload:
            if age < 5 and cpu_util < 50:
                strategy = "Refactor"
                instance = f"{target_cloud} App Service/Elastic Beanstalk + Auto-scaling"
                rationale = "Modern web application - refactor to PaaS for better scalability and reduced ops"
                effort = "High"
                confidence = 80
            else:
                strategy = "Replatform"
                instance = get_instance_by_specs(r, target_cloud)
                rationale = "Web server - replatform with load balancing and auto-scaling groups"
                effort = "Medium"
                confidence = 85
        
        elif "batch" in workload or "processing" in workload:
            if fault_tolerant:
                strategy = "Replatform"
                instance = f"{target_cloud} Batch/Glue/Dataflow"
                rationale = "Batch processing - replatform to cloud-native batch service for cost optimization"
                effort = "Medium"
                confidence = 88
            else:
                strategy = "Rehost"
                instance = get_instance_by_specs(r, target_cloud)
                rationale = "Batch processing - rehost initially, consider serverless options later"
                effort = "Low"
                confidence = 92
        
        elif "file" in workload or "storage" in workload:
            strategy = "Replatform"
            instance = f"{target_cloud} Storage (S3/Blob/GCS)"
            rationale = "File server - replatform to cloud object storage for durability and cost"
            effort = "Low"
            confidence = 95
        
        elif age > 8 or r.get('end_of_life', False):
            strategy = "Retire"
            instance = "Decommission"
            rationale = "Old server approaching EOL - evaluate if application is still needed"
            effort = "Low"
            confidence = 70
        
        else:
            # Default to rehost
            strategy = "Rehost"
            instance = get_instance_by_specs(r, target_cloud)
            rationale = f"General workload - lift and shift to equivalent {target_cloud} instance"
            effort = "Low"
            confidence = 90
        
        strategy_counts[strategy] = strategy_counts.get(strategy, 0) + 1
        
        # Calculate cost
        monthly_cost = estimate_cloud_cost(instance, target_cloud)
        total_cost += monthly_cost
        
        recommendations.append({
            "onprem_name": r['name'],
            "migration_strategy": strategy,
            "cloud_provider": target_cloud if target_cloud != "Multi-Cloud (All)" else "AWS/Azure/GCP",
            "cloud_instance": instance,
            "monthly_cost": round(monthly_cost, 2),
            "confidence": confidence,
            "migration_effort": effort,
            "rationale": rationale,
            "next_steps": get_next_steps(strategy, instance, target_cloud),
            "onprem_specs": {
                "cpu": r['cpu_cores'],
                "ram": r['ram_gb'],
                "storage": r['storage_gb'],
                "workload": r['workload_type']
            }
        })
    
    # Determine primary strategy
    primary_strategy = max(strategy_counts, key=strategy_counts.get)
    
    # Generate phased migration plan
    phases = []
    
    if strategy_counts.get("Retire", 0) > 0:
        phases.append({
            "phase": "1. Decommission",
            "description": f"Retire {strategy_counts['Retire']} obsolete servers",
            "timeline": "Week 1-2"
        })
    
    if strategy_counts.get("Rehost", 0) > 0:
        phases.append({
            "phase": "2. Lift & Shift",
            "description": f"Rehost {strategy_counts['Rehost']} servers as-is",
            "timeline": "Week 2-4"
        })
    
    if strategy_counts.get("Replatform", 0) > 0:
        phases.append({
            "phase": "3. Replatform",
            "description": f"Optimize {strategy_counts['Replatform']} workloads with managed services",
            "timeline": "Month 2-3"
        })
    
    if strategy_counts.get("Refactor", 0) > 0:
        phases.append({
            "phase": "4. Refactor",
            "description": f"Modernize {strategy_counts['Refactor']} applications to cloud-native",
            "timeline": "Month 3-6"
        })
    
    return {
        "summary": {
            "total_servers": len(onprem_resources),
            "estimated_monthly_cost": round(total_cost, 2),
            "primary_strategy": primary_strategy,
            "strategy_breakdown": strategy_counts
        },
        "recommendations": recommendations,
        "migration_plan": {
            "phases": phases,
            "total_timeline": "3-6 months"
        }
    }

def get_instance_by_specs(resource, target_cloud):
    """Helper to get instance type based on specs"""
    cpu = resource['cpu_cores']
    ram = resource['ram_gb']
    
    # Simple mapping logic
    if target_cloud == "AWS":
        if cpu <= 2 and ram <= 4:
            return "t3.medium"
        elif cpu <= 4 and ram <= 16:
            return "m5.xlarge"
        elif cpu <= 8 and ram <= 32:
            return "m5.2xlarge"
        elif cpu <= 16 and ram <= 64:
            return "c5.4xlarge"
        else:
            return "c5.9xlarge"
    elif target_cloud == "Azure":
        if cpu <= 2 and ram <= 4:
            return "B4ms"
        elif cpu <= 4 and ram <= 16:
            return "D4s v3"
        elif cpu <= 8 and ram <= 32:
            return "D8s v3"
        else:
            return "D16s v3"
    else:  # GCP
        if cpu <= 2 and ram <= 4:
            return "e2-medium"
        elif cpu <= 4 and ram <= 16:
            return "n2-standard-4"
        elif cpu <= 8 and ram <= 32:
            return "n2-standard-8"
        else:
            return "n2-standard-16"

def estimate_cloud_cost(instance, provider):
    """Estimate monthly cost"""
    # Simplified pricing
    pricing = {
        "t3.medium": 30, "m5.xlarge": 160, "m5.2xlarge": 320,
        "c5.4xlarge": 580, "c5.9xlarge": 1300,
        "B4ms": 100, "D4s v3": 140, "D8s v3": 280, "D16s v3": 560,
        "e2-medium": 24, "n2-standard-4": 140, "n2-standard-8": 280,
        "n2-standard-16": 560, "RDS for SQL Server/Oracle": 500,
        f"{provider} DocumentDB": 400, f"{provider} App Service": 300,
        f"{provider} Batch": 200, f"{provider} Storage": 50
    }
    return pricing.get(instance, 200)

def get_next_steps(strategy, instance, provider):
    """Get next steps based on strategy"""
    steps = {
        "Rehost": [
            f"Create {provider} account and VPC",
            f"Set up {instance} with matching OS",
            "Migrate data using AWS SMS/Azure Migrate",
            "Test application functionality",
            "Update DNS to point to new instance"
        ],
        "Replatform": [
            f"Provision {instance} in {provider}",
            "Configure backup and disaster recovery",
            "Set up monitoring and alerting",
            "Migrate data with minimal downtime",
            "Test and validate performance"
        ],
        "Refactor": [
            "Analyze application architecture",
            f"Design cloud-native solution using {provider} services",
            "Develop new components",
            "Set up CI/CD pipeline",
            "Phase migration with blue-green deployment"
        ],
        "Retire": [
            "Verify application is no longer needed",
            "Archive data if required",
            "Decommission server",
            "Update documentation"
        ]
    }
    return steps.get(strategy, ["Consult with migration team"])

###tab5 function ends here
# ===== HELPER FUNCTIONS =====

def get_instance_by_specs(resource, target_cloud):
    """Get appropriate cloud instance based on specs"""
    cpu = resource['cpu_cores']
    ram = resource['ram_gb']
    
    # Adjust based on utilization
    cpu_adj = max(1, round(cpu * resource.get('cpu_utilization', 30) / 100))
    ram_adj = max(1, round(ram * resource.get('memory_utilization', 40) / 100))
    
    if target_cloud == "AWS":
        if cpu_adj <= 2 and ram_adj <= 4:
            return "t3.medium"
        elif cpu_adj <= 4 and ram_adj <= 16:
            return "m5.xlarge"
        elif cpu_adj <= 8 and ram_adj <= 32:
            return "m5.2xlarge"
        elif cpu_adj <= 16 and ram_adj <= 64:
            return "c5.4xlarge"
        else:
            return "c5.9xlarge"
    
    elif target_cloud == "Azure":
        if cpu_adj <= 2 and ram_adj <= 4:
            return "B4ms"
        elif cpu_adj <= 4 and ram_adj <= 16:
            return "D4s v3"
        elif cpu_adj <= 8 and ram_adj <= 32:
            return "D8s v3"
        else:
            return "D16s v3"
    
    elif target_cloud == "GCP":
        if cpu_adj <= 2 and ram_adj <= 4:
            return "e2-medium"
        elif cpu_adj <= 4 and ram_adj <= 16:
            return "n2-standard-4"
        elif cpu_adj <= 8 and ram_adj <= 32:
            return "n2-standard-8"
        else:
            return "n2-standard-16"
    
    else:  # Multi-Cloud
        return "Varies by provider"

def estimate_cloud_cost_by_specs(resource, provider, strategy):
    """Estimate monthly cloud cost"""
    cpu = resource['cpu_cores']
    
    # Base cost per core (simplified)
    base_cost_per_core = {
        "AWS": 30,
        "Azure": 28,
        "GCP": 25
    }
    
    cost_per_core = base_cost_per_core.get(provider, 30)
    
    # Adjust based on strategy
    if strategy == "Replatform":
        cost_per_core *= 1.2  # Managed services cost more
    elif strategy == "Refactor":
        cost_per_core *= 0.8   # Serverless can be cheaper
    
    return cpu * cost_per_core

def get_effort_by_strategy(strategy):
    """Get migration effort level by strategy"""
    effort_map = {
        "Retire": "Low",
        "Rehost": "Low",
        "Replatform": "Medium",
        "Refactor": "High",
        "Retain": "None"
    }
    return effort_map.get(strategy, "Medium")

def get_next_steps_by_strategy(strategy, provider, resource):
    """Get next steps based on migration strategy"""
    
    common_steps = [
        f"Create {provider} account and set up VPC/network",
        "Set up VPN/Direct Connect for hybrid connectivity"
    ]
    
    strategy_steps = {
        "Rehost": [
            f"Create {get_instance_by_specs(resource, provider)} with matching OS",
            "Migrate data using AWS SMS/Azure Migrate",
            "Test application functionality",
            "Update DNS to point to new instance"
        ],
        "Replatform": [
            f"Provision managed service ({get_instance_by_specs(resource, provider)})",
            "Configure backup and disaster recovery",
            "Set up monitoring and alerting",
            "Migrate data with minimal downtime"
        ],
        "Refactor": [
            "Analyze application architecture",
            f"Design cloud-native solution using {provider} services",
            "Develop new components",
            "Set up CI/CD pipeline",
            "Phase migration with blue-green deployment"
        ],
        "Retire": [
            "Verify application is no longer needed",
            "Archive data if required",
            "Decommission server",
            "Update documentation"
        ],
        "Retain": [
            "Document decision to retain on-premises",
            "Review compliance requirements",
            "Plan for future migration"
        ]
    }
    
    return common_steps + strategy_steps.get(strategy, [])
### new changes end here for tab5

def _safe_to_dict(raw: Any) -> Dict[str, Any]:
    """Accept dict or JSON-string and return a dict; else empty dict."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}
    return {}

def _to_dataframe(prices: Dict[str, Any]) -> pd.DataFrame:
    """
    Normalize API shape into tidy data.
    Expected keys: aws_pricing_tool / azure_pricing_tool / gcp_pricing_tool
    Each can be a dict or a JSON string.
    """
    rows: List[Dict[str, Any]] = []
    for provider_key, payload in prices.items():
        # Skip metadata keys
        if provider_key.startswith('_') or provider_key == 'metadata':
            continue
            
        data = _safe_to_dict(payload)
        if not data:
            continue

        provider = data.get("provider") or provider_key.replace("_pricing_tool", "").upper()
        hourly = data.get("hourly_rate") or data.get("hourly")
        monthly = data.get("monthly_rate") or data.get("monthly")
        currency = data.get("currency", "USD")
        pricing_model = data.get("pricing_model", "On-Demand")
        region = data.get("region") or (data.get("specifications") or {}).get("region")

        # Keep only valid numeric rows
        if hourly is None and monthly is None:
            continue

        rows.append({
            "provider": provider,
            "region": region,
            "pricing_model": pricing_model,
            "currency": currency,
            "hourly_rate": float(hourly) if hourly is not None else None,
            "monthly_rate": float(monthly) if monthly is not None else None,
        })

    return pd.DataFrame(rows)

def display_price_chart(data, instance_type, region):
    """Display price comparison chart"""
    st.subheader(f"💰 Price Comparison: {instance_type} in {region}")
    
    # Extract data for plotting
    providers = []
    monthly_costs = []
    hourly_rates = []
    currencies = []
    
    if isinstance(data, dict):
        for provider, values in data.items():
            if provider != '_metadata' and isinstance(values, dict):
                providers.append(provider.upper())
                monthly = values.get('monthly_rate', values.get('monthly', 0))
                monthly_costs.append(float(monthly) if monthly else 0)
                hourly = values.get('hourly_rate', values.get('hourly', 0))
                hourly_rates.append(float(hourly) if hourly else 0)
                currencies.append(values.get('currency', 'USD'))
    
    if providers and monthly_costs:
        df = pd.DataFrame({
            'Provider': providers,
            'Monthly Cost ($)': monthly_costs,
            'Hourly Rate ($)': hourly_rates,
            'Currency': currencies
        })
        
        # Sort by cost
        df = df.sort_values('Monthly Cost ($)')
        
        # Display metrics
        col1, col2, col3 = st.columns(3)
        with col1:
            cheapest = df.iloc[0]
            st.metric("Cheapest Provider", cheapest['Provider'], 
                     f"${cheapest['Monthly Cost ($)']:.2f}")
        with col2:
            avg_cost = df['Monthly Cost ($)'].mean()
            st.metric("Average Cost", f"${avg_cost:.2f}")
        with col3:
            if len(df) > 1:
                savings = df['Monthly Cost ($)'].max() - df['Monthly Cost ($)'].min()
                st.metric("Max Savings", f"${savings:.2f}")
        
        # Create bar chart
        fig = px.bar(
            df,
            x='Provider',
            y='Monthly Cost ($)',
            title=f"Monthly Cost Comparison - {instance_type} in {region}",
            color='Provider',
            text_auto='.2f'
        )
        
        fig.update_layout(
            yaxis_title="Monthly Cost (USD)",
            showlegend=False,
            height=500
        )
        
        st.plotly_chart(fig, use_container_width=True)
        
        # Detailed table
        st.subheader("📋 Detailed Pricing")
        st.dataframe(df, use_container_width=True)
    else:
        st.warning("No price data available")
        if '_metadata' in data:
            st.json(data['_metadata'])

def render_enhanced_pricing_dashboard(response):
    """Render enhanced pricing dashboard with charts and tables"""
    try:
        if response.status_code != 200:
            st.error(f"API error: {response.text}")
            return

        raw = response.json()
        df = _to_dataframe(raw)

        if df.empty:
            st.warning("No valid pricing data received from API.")
            with st.expander("Raw API payload"):
                st.json(raw)
            return

        # Normalize currency
        currency = df["currency"].dropna().iloc[0] if not df["currency"].dropna().empty else "USD"

        # Calculate monthly effective rate
        df["monthly_effective"] = df.apply(
            lambda r: r["monthly_rate"]
            if pd.notna(r["monthly_rate"])
            else (r["hourly_rate"] * 730 if pd.notna(r["hourly_rate"]) else None),
            axis=1
        )

        # Drop rows missing monthly_effective
        df_plot = df.dropna(subset=["monthly_effective"]).copy()
        if df_plot.empty:
            st.warning("No billable rates found to plot.")
            with st.expander("Parsed DataFrame"):
                st.dataframe(df)
            return

        # Find cheapest provider
        cheapest_idx = df_plot["monthly_effective"].idxmin()
        cheapest_row = df_plot.loc[cheapest_idx]
        cheapest_provider = cheapest_row["provider"]
        cheapest_cost = float(cheapest_row["monthly_effective"])

        df_plot["savings_abs"] = df_plot["monthly_effective"] - cheapest_cost
        df_plot["savings_pct"] = df_plot["savings_abs"] / df_plot["monthly_effective"] * 100
        df_plot["label_monthly"] = df_plot.apply(
            lambda r: format_currency(r["monthly_effective"], currency), axis=1
        )

        # KPI cards
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("Cheapest Provider", cheapest_provider)
        with c2:
            st.metric("Cheapest Monthly Cost", format_currency(cheapest_cost, currency))
        with c3:
            max_savings = df_plot.loc[df_plot["provider"] != cheapest_provider, "savings_abs"].max()
            if pd.notna(max_savings):
                st.metric("Max Monthly Savings", format_currency(max_savings, currency))
            else:
                st.metric("Max Monthly Savings", "-")

        # Monthly bar chart
        st.subheader("Monthly Cost Comparison")
        fig_monthly = px.bar(
            df_plot.sort_values("monthly_effective"),
            x="provider",
            y="monthly_effective",
            color="provider",
            text="label_monthly",
            hover_data=["pricing_model", "region", "currency"],
            title="Monthly Cloud Cost (Effective)",
        )
        fig_monthly.update_traces(textposition="outside")
        fig_monthly.update_layout(
            yaxis_title=f"Monthly Cost ({currency})",
            xaxis_title="Provider",
            showlegend=False,
        )
        st.plotly_chart(fig_monthly, use_container_width=True)

        # Hourly chart if available
        if df_plot["hourly_rate"].notna().any():
            st.subheader("Hourly Cost Comparison")
            df_hourly = df_plot.dropna(subset=["hourly_rate"]).copy()
            df_hourly["label_hourly"] = df_hourly.apply(
                lambda r: format_currency(r["hourly_rate"], currency), axis=1
            )
            fig_hourly = px.bar(
                df_hourly.sort_values("hourly_rate"),
                x="provider",
                y="hourly_rate",
                color="provider",
                text="label_hourly",
                hover_data=["pricing_model", "region", "currency"],
                title="Hourly Cloud Cost",
            )
            fig_hourly.update_traces(textposition="outside")
            st.plotly_chart(fig_hourly, use_container_width=True)

        # Pie chart
        st.subheader("Monthly Spend Share")
        fig_pie = px.pie(
            df_plot,
            names="provider",
            values="monthly_effective",
            hole=0.35,
            title="Share of Monthly Cost by Provider"
        )
        st.plotly_chart(fig_pie, use_container_width=True)

        # Data table
        st.subheader("Detailed Pricing (Normalized)")
        nice_df = df_plot[[
            "provider", "region", "pricing_model", "currency",
            "hourly_rate", "monthly_rate", "monthly_effective",
            "savings_abs", "savings_pct"
        ]].copy()

        # Format for display
        display_df = nice_df.copy()
        display_df["hourly_rate"] = display_df["hourly_rate"].apply(
            lambda v: format_currency(v, currency) if pd.notna(v) else "-"
        )
        display_df["monthly_rate"] = display_df["monthly_rate"].apply(
            lambda v: format_currency(v, currency) if pd.notna(v) else "-"
        )
        display_df["monthly_effective"] = display_df["monthly_effective"].apply(
            lambda v: format_currency(v, currency)
        )
        display_df["savings_abs"] = display_df["savings_abs"].apply(
            lambda v: format_currency(v, currency) if pd.notna(v) else "-"
        )
        display_df["savings_pct"] = display_df["savings_pct"].apply(
            lambda v: f"{v:,.1f}%" if pd.notna(v) else "-"
        )

        st.dataframe(display_df, use_container_width=True)

        # Download button
        csv = nice_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="Download CSV (Normalized Pricing)",
            data=csv,
            file_name="cloud_pricing_comparison.csv",
            mime="text/csv"
        )

        # Raw payloads
        st.markdown("### Provider Payloads")
        for k, v in raw.items():
            if not k.startswith('_'):
                with st.expander(k.upper()):
                    parsed = _safe_to_dict(v)
                    st.json(parsed if parsed else v)

    except Exception as ex:
        st.error(f"Error while rendering pricing dashboard: {ex}")
        import traceback
        st.code(traceback.format_exc())
        
def run_analysis_sync(agent, request):
    """Run async analysis in a synchronous way for Streamlit"""
    import asyncio
    import threading
    
    result_container = []
    error_container = []
    
    def run_async():
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            # FIX: Use asyncio.run() which handles loop cleanup properly
            result = loop.run_until_complete(
                asyncio.wait_for(
                    agent.analyze_with_llm(request),
                    timeout=30
                )
            )
            loop.close()
            result_container.append(result)
        except asyncio.TimeoutError:
            error_container.append("timeout")
        except Exception as e:
            error_container.append(str(e))
    
    thread = threading.Thread(target=run_async)
    thread.start()
    thread.join(timeout=35)
    
    if error_container:
        return {"error": error_container[0], "mode": "error"}
    return result_container[0] if result_container else {"error": "No result", "mode": "error"}

# ===== SESSION STATE INITIALIZATION =====
if 'agent' not in st.session_state:
    st.session_state.agent = None
if 'resources' not in st.session_state:
    st.session_state.resources = []
if 'analysis_result' not in st.session_state:
    st.session_state.analysis_result = None
if 'api_mode' not in st.session_state:
    st.session_state.api_mode = False  # False = local mode, True = API mode
if 'api_url' not in st.session_state:
    st.session_state.api_url = "http://localhost:8080"
if 'constraints' not in st.session_state:
    st.session_state.constraints = {
        "max_budget": 10000.0,
        "availability": "99.9%",
        "compliance": [],
        "risk_tolerance": "medium",
        "optimization_goals": ["cost_reduction"]
    }
if 'creds' not in st.session_state:
    st.session_state.creds = {
        'aws': False,
        'azure': False,
        'gcp': False,
        'openai': False
    }
if 'use_llm' not in st.session_state:
    st.session_state.use_llm = False
if 'operation_in_progress' not in st.session_state:
    st.session_state.operation_in_progress = False

# ===== CUSTOM CSS =====
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        color: #1E88E5;
        text-align: center;
        margin-bottom: 2rem;
    }
    .metric-card {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
        text-align: center;
    }
    .recommendation-card {
        background-color: #e8f4fd;
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 0.5rem 0;
        border-left: 4px solid #1E88E5;
    }
    .savings-positive {
        color: #00C853;
        font-weight: bold;
    }
    .stButton button {
        width: 100%;
    }
</style>
""", unsafe_allow_html=True)

# ===== SIDEBAR - COMPLETE FIXED VERSION WITH ERROR CLEARING =====
with st.sidebar:
    st.image("https://img.icons8.com/color/96/000000/cloud--v1.png", width=80)
    st.title("Cloud Rationalization Agent")
    
    # ===== MODE SELECTION =====
    st.header("⚙️ Operation Mode")
    
    # Initialize mode in session state if not present
    if 'selected_mode' not in st.session_state:
        st.session_state.selected_mode = "🔧 Tool-Only Mode (Faster)"
    
    # Radio button for mode selection
    mode = st.radio(
        "Select how to run the agent:",
        ["🧠 LLM Mode (AI Explanations)", "🔧 Tool-Only Mode (Faster)"],
        index=0 if st.session_state.selected_mode == "🧠 LLM Mode (AI Explanations)" else 1,
        key="mode_radio"
    )
    
    # FIX: Clear all error states when mode changes
    #if mode != st.session_state.selected_mode:
    if mode != st.session_state.get('prev_mode'):
        #st.session_state.selected_mode = mode
            # Just clear any error flags
        if 'connection_error' in st.session_state:
            del st.session_state.connection_error
        if 'quota_error' in st.session_state:
            del st.session_state.quota_error
        
        st.session_state.prev_mode = mode
        st.warning("Mode changed. Please re-initialize the agent.")

        # Clear ALL error-related session state variables
        error_keys = ['connection_error', 'quota_error', 'analysis_error', 
                     'error_type', 'error_message', 'llm_failure']
        for key in error_keys:
            if key in st.session_state:
                del st.session_state[key]
        
        # Reset the agent if needed? No - let user re-initialize
        # But clear any stale error flags
        st.success(f"Switched to {mode}. Please re-initialize the agent.")
        st.rerun()
    
    # Set LLM flag based on mode
    st.session_state.use_llm = "LLM Mode" in mode
    
    # ===== AUTO-DETECT CREDENTIALS FROM .ENV =====
    env_openai = os.getenv("OPENAI_API_KEY")
    env_aws_key = os.getenv("AWS_ACCESS_KEY_ID")
    env_aws_secret = os.getenv("AWS_SECRET_ACCESS_KEY")
    env_azure = os.getenv("AZURE_SUBSCRIPTION_KEY")
    env_gcp = os.getenv("GCP_CREDENTIALS_PATH")
    
    # ===== CREDENTIAL STATUS DISPLAY =====
    st.header("🔑 Detected Credentials")
    
    col1, col2 = st.columns(2)
    with col1:
        if env_openai:
            st.success("✅ OpenAI")
        else:
            st.info("⬜ OpenAI (not found)")
    
    with col2:
        if env_aws_key and env_aws_secret:
            st.success("✅ AWS")
        else:
            st.info("⬜ AWS (not found)")
    
    col1, col2 = st.columns(2)
    with col1:
        if env_azure:
            st.success("✅ Azure")
        else:
            st.info("⬜ Azure (not found)")
    
    with col2:
        if env_gcp:
            st.success("✅ GCP")
        else:
            st.info("⬜ GCP (not found)")
    
    # ===== MODE-SPECIFIC WARNINGS =====
    if st.session_state.use_llm and not env_openai:
        st.error("❌ LLM Mode selected but no OpenAI API key found in .env")
        st.info("ℹ️ The agent will initialize in Tool-Only Mode until you add OPENAI_API_KEY to .env")
        st.session_state.use_llm = False
    
    # ===== INITIALIZE AGENT BUTTON =====
    if st.button("🚀 Initialize Agent", type="primary", key="init_agent_button"):
        with st.spinner("Initializing agent..."):
            try:
                # Prepare credentials
                aws_creds = None
                if env_aws_key and env_aws_secret:
                    aws_creds = {
                        'aws_access_key_id': env_aws_key,
                        'aws_secret_access_key': env_aws_secret
                    }
                
                azure_creds = None
                if env_azure:
                    azure_creds = {'subscription_key': env_azure}
                
                gcp_creds = None
                if env_gcp:
                    gcp_creds = {'credentials_path': env_gcp}
                
                # IMPORTANT: Only pass OpenAI key if in LLM mode AND key exists
                openai_key = env_openai if (st.session_state.use_llm and env_openai) else None
                
                if openai_key:
                    st.info("🧠 Initializing in LLM Mode...")
                else:
                    st.info("🔧 Initializing in Tool-Only Mode...")
                
                # Clear any previous error states before initializing
                error_keys = ['connection_error', 'quota_error', 'analysis_error', 
                            'error_type', 'error_message', 'llm_failure']
                for key in error_keys:
                    if key in st.session_state:
                        del st.session_state[key]

                # CRITICAL FIX: Explicitly set openai_api_key based on mode
                if st.session_state.use_llm:
                    # LLM Mode - use the key from env
                    openai_key = env_openai
                    st.info("🧠 Initializing in LLM Mode...")
                else:
                    # Tool Mode - EXPLICITLY set to None, even if env has key
                    openai_key = None
                    st.info("🔧 Initializing in Tool-Only Mode...")

                # Initialize agent
                st.session_state.agent = CloudRationalizationAgent(
                    openai_api_key=openai_key,
                    aws_credentials=aws_creds,
                    azure_credentials=azure_creds,
                    gcp_credentials=gcp_creds
                )
                
                # Store credential status
                st.session_state.creds = {
                    'aws': bool(aws_creds),
                    'azure': bool(azure_creds),
                    'gcp': bool(gcp_creds),
                    'openai': bool(openai_key)
                }
                
                actual_mode = "LLM MODE" if st.session_state.agent.llm else "TOOL-ONLY MODE"
                st.success(f"✅ Agent initialized in {actual_mode}!")
                
            except Exception as e:
                st.error(f"Failed to initialize: {e}")
                import traceback
                st.code(traceback.format_exc())
    
    st.markdown("---")
    
    # ===== API MODE TOGGLE =====
    st.header("🌐 API Mode")
    st.markdown("Connect to a remote agent server")
    
    # Initialize API mode in session state
    if 'api_mode' not in st.session_state:
        st.session_state.api_mode = False
    
    # Store previous API mode to detect changes
    previous_api_mode = st.session_state.api_mode
    
    use_api = st.checkbox("Use API Mode instead", value=st.session_state.api_mode, key="use_api_checkbox")
    
    # FIX: Clear errors when toggling API mode
    if use_api != previous_api_mode:
        st.session_state.api_mode = use_api
        # Clear error states on API mode toggle
        error_keys = ['connection_error', 'quota_error', 'analysis_error', 
                     'error_type', 'error_message']
        for key in error_keys:
            if key in st.session_state:
                del st.session_state[key]
        st.rerun()
    
    if use_api:
        st.session_state.api_mode = True
        st.session_state.api_url = st.text_input(
            "API URL",
            value=st.session_state.get('api_url', 'http://localhost:8080'),
            help="URL of the FastAPI backend",
            key="api_url_input"
        )
        
        if st.button("🔍 Check API Health", key="check_api_button"):
            with st.spinner("Checking API status..."):
                try:
                    response = requests.get(f"{st.session_state.api_url}/health", timeout=5)
                    if response.status_code == 200:
                        data = response.json()
                        st.success(f"✅ API is healthy (Mode: {data.get('agent_mode', 'unknown')})")
                        # Clear any API errors on success
                        if 'api_error' in st.session_state:
                            del st.session_state.api_error
                    else:
                        st.error(f"❌ API returned error: {response.status_code}")
                        st.session_state.api_error = True
                except requests.exceptions.ConnectionError:
                    st.error(f"❌ Cannot connect to API at {st.session_state.api_url}")
                    st.info("💡 Make sure the API server is running: `uvicorn api.main:app --reload --port 8080`")
                    st.session_state.api_error = True
                except Exception as e:
                    st.error(f"❌ Error: {e}")
                    st.session_state.api_error = True
    else:
        st.session_state.api_mode = False
    
    st.markdown("---")
    
    # ===== RESOURCE STATS =====
    st.markdown("### 📊 Resource Stats")
    
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Total Resources", len(st.session_state.resources))
    with col2:
        if st.session_state.resources:
            total_cost = sum(r.get('monthly_cost', 0) for r in st.session_state.resources)
            st.metric("Total Cost", f"${total_cost:,.0f}")
        else:
            st.metric("Total Cost", "$0")
    
    # ===== LIVE PRICING STATUS =====
    if st.session_state.get('creds') and not st.session_state.api_mode:
        st.markdown("### 🔑 Live Pricing For:")
        live = []
        if st.session_state.creds.get('aws'):
            live.append("AWS")
        if st.session_state.creds.get('azure'):
            live.append("Azure")
        if st.session_state.creds.get('gcp'):
            live.append("GCP")
        
        if live:
            st.success(f"✅ {', '.join(live)}")
        else:
            st.info("ℹ️ All providers using demo pricing")
    
    # ===== CLEAR BUTTON =====
    if st.button("🗑️ Clear All Resources", key="clear_button"):
        if st.session_state.resources:
            st.session_state.resources = []
            st.session_state.analysis_result = None
            # Clear any errors when clearing resources
            error_keys = ['connection_error', 'quota_error', 'analysis_error', 
                         'error_type', 'error_message']
            for key in error_keys:
                if key in st.session_state:
                    del st.session_state[key]
            st.success("✅ All resources cleared!")
            st.rerun()
        else:
            st.warning("No resources to clear")


# ===== MAIN HEADER =====
st.markdown("<h1 class='main-header'>☁️ Cloud Infrastructure Optimizer</h1>", unsafe_allow_html=True)

# ===== TABS =====
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📋 Infrastructure Input", 
    "💰 Price Comparison", 
    "📈 Analysis Results",
    "📊 Reports",
    "🏢 On-Prem to Cloud Migration"  # New tab
])

# ===== TAB 1: Infrastructure Input =====
with tab1:
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("Add Cloud Resource")
        
        with st.form("resource_form"):
            # Row 1: Basic info
            row1_col1, row1_col2, row1_col3 = st.columns(3)
            with row1_col1:
                resource_name = st.text_input("Resource Name", value="web-server-01")
            with row1_col2:
                provider = st.selectbox(
                    "Cloud Provider",
                    options=[p.value for p in CloudProvider],
                    format_func=lambda x: x.upper()
                )
            with row1_col3:
                resource_type = st.selectbox(
                    "Resource Type",
                    options=[r.value for r in ResourceType],
                    format_func=lambda x: x.upper(),
                    index=0
                )
            
            # Row 2: Instance details
            row2_col1, row2_col2, row2_col3 = st.columns(3)
            with row2_col1:
                instance_type = st.text_input("Instance Type", value="t3.medium")
            with row2_col2:
                region = st.text_input("Region", value="us-east-1")
            with row2_col3:
                quantity = st.number_input("Quantity", min_value=1, value=1)
            
            # Row 3: Cost and usage
            row3_col1, row3_col2, row3_col3 = st.columns(3)
            with row3_col1:
                monthly_cost = st.number_input(
                    "Current Monthly Cost ($)",
                    min_value=0.0,
                    value=100.0,
                    step=10.0
                )
            with row3_col2:
                usage_pattern = st.selectbox(
                    "Usage Pattern",
                    options=[u.value for u in UsagePattern],
                    format_func=lambda x: x.upper()
                )
            with row3_col3:
                criticality = st.select_slider(
                    "Criticality",
                    options=["low", "medium", "high"],
                    value="medium"
                )
            
            # Row 4: Additional options
            row4_col1, row4_col2 = st.columns(2)
            with row4_col1:
                fault_tolerant = st.checkbox("Fault Tolerant")
            with row4_col2:
                auto_scaling = st.checkbox("Auto Scaling Enabled")
            
            # EXPANDED SPECIFICATIONS
            with st.expander("💻 Detailed Specifications"):
                spec_col1, spec_col2, spec_col3 = st.columns(3)
                with spec_col1:
                    os_type = st.selectbox("Operating System", ["Linux", "Windows", "Other"])
                    cpu = st.number_input("vCPU Cores", min_value=1, value=2)
                with spec_col2:
                    memory = st.number_input("Memory (GB)", min_value=0.5, value=8.0, step=0.5)
                    storage_type = st.selectbox("Storage Type", ["SSD", "HDD", "NVMe"])
                with spec_col3:
                    storage = st.number_input("Storage (GB)", min_value=10, value=100, step=10)
                    network = st.selectbox("Network Performance", ["Low", "Medium", "High"])
            
            submitted = st.form_submit_button("➕ Add Resource", type="primary")
            
            if submitted:
                new_resource = {
                    "name": resource_name,
                    "provider": provider,
                    "resource_type": resource_type,
                    "region": region,
                    "instance_type": instance_type,
                    "quantity": quantity,
                    "usage_pattern": usage_pattern,
                    "monthly_cost": monthly_cost,
                    "fault_tolerant": fault_tolerant,
                    "criticality": criticality,
                    "auto_scaling": auto_scaling,
                    "specifications": {
                        "os": os_type,
                        "cpu": cpu,
                        "memory": memory,
                        "storage": storage,
                        "storage_type": storage_type,
                        "network": network,
                        "instance_type": instance_type
                    }
                }
                # Append to session state WITHOUT rerun
                st.session_state.resources.append(new_resource)
                st.success(f"✅ Added {resource_name} (Total: {len(st.session_state.resources)} resources)")
        
        # ===== NEW: IMPORT CLOUD RESOURCES SECTION =====
        st.subheader("📤 Import Cloud Resources from File")
        
        with st.expander("Import from CSV/Excel", expanded=False):
            st.markdown("""
            **Supported formats:** CSV, Excel (.xlsx, .xls)
            
            **Required columns:**
            - `name` - Resource name
            - `provider` - aws/azure/gcp
            - `instance_type` - e.g., t3.medium, D2s v3, n1-standard-1
            - `region` - e.g., us-east-1, eastus, us-central1
            - `monthly_cost` - Current monthly cost in USD
            
            **Optional columns:**
            - `resource_type` - compute/storage/database (default: compute)
            - `quantity` - Number of instances (default: 1)
            - `usage_pattern` - steady/variable/batch (default: steady)
            - `fault_tolerant` - TRUE/FALSE (default: FALSE)
            - `criticality` - low/medium/high (default: medium)
            - `os` - Operating system (default: Linux)
            - `cpu` - Number of vCPU cores
            - `memory` - RAM in GB
            - `storage` - Storage in GB
            """)
            
            uploaded_file = st.file_uploader(
                "Choose file",
                type=['csv', 'xlsx', 'xls'],
                key="cloud_import_uploader"
            )
            
            if uploaded_file is not None:
                try:
                    import pandas as pd
                    
                    # Read file
                    if uploaded_file.name.endswith('.csv'):
                        df = pd.read_csv(uploaded_file, skipinitialspace=True)
                        # Clean column names
                        df.columns = df.columns.str.strip().str.lower().str.replace(' ', '_')
                    else:
                        df = pd.read_excel(uploaded_file)
                        df.columns = df.columns.str.strip().str.lower().str.replace(' ', '_')
                    
                    # Replace NaN with empty string
                    df = df.fillna('')
                    
                    st.success(f"✅ File loaded: {len(df)} resources found")
                    
                    # Show preview
                    st.markdown("**Preview Data:**")
                    st.dataframe(df.head(10), use_container_width=True, hide_index=True)
                    
                    # Column mapping
                    st.markdown("**Map Columns to Your File**")
                    
                    # Create column lists
                    all_columns = list(df.columns)
                    columns_with_na = ['Not in file'] + all_columns
                    
                    # Required columns mapping
                    col_req1, col_req2, col_req3 = st.columns(3)
                    
                    with col_req1:
                        name_col = st.selectbox(
                            "Resource Name column",
                            all_columns,
                            index=_find_column_index_fixed(df, ['name', 'resource_name', 'resource'])
                        )
                        
                        provider_col = st.selectbox(
                            "Provider column",
                            all_columns,
                            index=_find_column_index_fixed(df, ['provider', 'cloud', 'cloud_provider'])
                        )
                    
                    with col_req2:
                        instance_col = st.selectbox(
                            "Instance Type column",
                            all_columns,
                            index=_find_column_index_fixed(df, ['instance_type', 'instance', 'type', 'instance-type'])
                        )
                        
                        region_col = st.selectbox(
                            "Region column",
                            all_columns,
                            index=_find_column_index_fixed(df, ['region', 'location', 'zone'])
                        )
                    
                    with col_req3:
                        cost_col = st.selectbox(
                            "Monthly Cost column",
                            all_columns,
                            index=_find_column_index_fixed(df, ['monthly_cost', 'cost', 'price', 'monthlycost'])
                        )
                    
                    # Optional columns mapping
                    st.markdown("**Optional Columns (leave as 'Not in file' if not present)**")
                    
                    col_opt1, col_opt2, col_opt3 = st.columns(3)
                    
                    with col_opt1:
                        resource_type_col = st.selectbox(
                            "Resource Type",
                            columns_with_na,
                            index=_find_column_index_with_na(df, ['resource_type', 'type', 'resource'])
                        )
                        
                        quantity_col = st.selectbox(
                            "Quantity",
                            columns_with_na,
                            index=_find_column_index_with_na(df, ['quantity', 'count', 'instances'])
                        )
                    
                    with col_opt2:
                        usage_col = st.selectbox(
                            "Usage Pattern",
                            columns_with_na,
                            index=_find_column_index_with_na(df, ['usage_pattern', 'usage', 'pattern'])
                        )
                        
                        ft_col = st.selectbox(
                            "Fault Tolerant",
                            columns_with_na,
                            index=_find_column_index_with_na(df, ['fault_tolerant', 'fault-tolerant', 'ha'])
                        )
                    
                    with col_opt3:
                        criticality_col = st.selectbox(
                            "Criticality",
                            columns_with_na,
                            index=_find_column_index_with_na(df, ['criticality', 'critical', 'priority'])
                        )
                        
                        os_col = st.selectbox(
                            "Operating System",
                            columns_with_na,
                            index=_find_column_index_with_na(df, ['os', 'operating_system', 'platform'])
                        )
                    
                    # Advanced specs in second row
                    col_adv1, col_adv2, col_adv3 = st.columns(3)
                    
                    with col_adv1:
                        cpu_col = st.selectbox(
                            "CPU Cores",
                            columns_with_na,
                            index=_find_column_index_with_na(df, ['cpu', 'cores', 'vcpu'])
                        )
                    
                    with col_adv2:
                        memory_col = st.selectbox(
                            "Memory (GB)",
                            columns_with_na,
                            index=_find_column_index_with_na(df, ['memory', 'ram', 'mem'])
                        )
                    
                    with col_adv3:
                        storage_col = st.selectbox(
                            "Storage (GB)",
                            columns_with_na,
                            index=_find_column_index_with_na(df, ['storage', 'disk', 'storage_gb'])
                        )
                    
                    if st.button("📥 Import Cloud Resources", type="primary"):
                        imported_count = 0
                        errors = []
                        
                        for idx, row in df.iterrows():
                            try:
                                # Helper functions for safe conversion
                                def safe_str(val):
                                    if pd.isna(val) or val == '':
                                        return ''
                                    return str(val).strip()
                                
                                def safe_float(val, default=0.0):
                                    if pd.isna(val) or val == '':
                                        return default
                                    try:
                                        return float(val)
                                    except (ValueError, TypeError):
                                        return default
                                
                                def safe_int(val, default=1):
                                    if pd.isna(val) or val == '':
                                        return default
                                    try:
                                        return int(float(val))
                                    except (ValueError, TypeError):
                                        return default
                                
                                def safe_bool(val, default=False):
                                    if pd.isna(val) or val == '':
                                        return default
                                    val_str = str(val).lower().strip()
                                    return val_str in ['true', 'yes', '1', 't', 'y', 'true']
                                
                                # Required fields
                                name = safe_str(row[name_col])
                                provider = safe_str(row[provider_col]).lower()
                                instance_type = safe_str(row[instance_col])
                                region = safe_str(row[region_col])
                                monthly_cost = safe_float(row[cost_col], 100.0)
                                
                                # Optional fields with defaults
                                resource_type = 'compute'
                                if resource_type_col != 'Not in file':
                                    resource_type = safe_str(row[resource_type_col]).lower()
                                    # Map any variations to our enum values
                                    resource_type_map = {
                                        'cache': 'cache',
                                        'redis': 'cache',
                                        'memcached': 'cache',
                                        'elasticache': 'cache',
                                        'message': 'message_queue',
                                        'queue': 'message_queue',
                                        'sqs': 'message_queue',
                                        'cdn': 'cdn',
                                        'cloudfront': 'cdn',
                                        'dns': 'dns',
                                        'route53': 'dns',
                                        'loadbalancer': 'load_balancer',
                                        'elb': 'load_balancer',
                                        'alb': 'load_balancer',
                                        'serverless': 'serverless',
                                        'lambda': 'serverless',
                                        'function': 'serverless',
                                        'container': 'container',
                                        'kubernetes': 'container',
                                        'eks': 'container',
                                        'aks': 'container',
                                        'gke': 'container',
                                        'database': 'database',
                                        'db': 'database',
                                        'rds': 'database',
                                        'storage': 'storage',
                                        's3': 'storage',
                                        'blob': 'storage'
                                    }
                                    resource_type = resource_type_map.get(resource_type, 'compute')
                                quantity = 1
                                if quantity_col != 'Not in file':
                                    quantity = safe_int(row[quantity_col], 1)
                                
                                usage_pattern = 'steady'
                                if usage_col != 'Not in file':
                                    usage_pattern = safe_str(row[usage_col]).lower()
                                
                                fault_tolerant = False
                                if ft_col != 'Not in file':
                                    fault_tolerant = safe_bool(row[ft_col], False)
                                
                                criticality = 'medium'
                                if criticality_col != 'Not in file':
                                    criticality = safe_str(row[criticality_col]).lower()
                                
                                os_type = 'Linux'
                                if os_col != 'Not in file':
                                    os_type = safe_str(row[os_col])
                                
                                cpu = 2
                                if cpu_col != 'Not in file':
                                    cpu = safe_int(row[cpu_col], 2)
                                
                                memory = 8
                                if memory_col != 'Not in file':
                                    memory = safe_float(row[memory_col], 8)
                                
                                storage = 100
                                if storage_col != 'Not in file':
                                    storage = safe_int(row[storage_col], 100)
                                
                                # Create resource
                                new_resource = {
                                    "name": name,
                                    "provider": provider,
                                    "resource_type": resource_type,
                                    "region": region,
                                    "instance_type": instance_type,
                                    "quantity": quantity,
                                    "usage_pattern": usage_pattern,
                                    "monthly_cost": monthly_cost,
                                    "fault_tolerant": fault_tolerant,
                                    "criticality": criticality,
                                    "auto_scaling": False,
                                    "specifications": {
                                        "os": os_type,
                                        "cpu": cpu,
                                        "memory": memory,
                                        "storage": storage,
                                        "instance_type": instance_type
                                    }
                                }
                                
                                st.session_state.resources.append(new_resource)
                                imported_count += 1
                                
                            except Exception as e:
                                errors.append(f"Row {idx + 2}: {str(e)}")
                        
                        if imported_count > 0:
                            st.success(f"✅ Successfully imported {imported_count} cloud resources!")
                        
                        if errors:
                            with st.expander(f"⚠️ {len(errors)} errors during import"):
                                for error in errors[:10]:
                                    st.error(error)
                        
                        st.rerun()
                
                except Exception as e:
                    st.error(f"Error reading file: {e}")    
    with col2:
        st.subheader("Business Constraints")
        with st.form("constraints_form"):
            max_budget = st.number_input(
                "Max Monthly Budget ($)",
                min_value=0.0,
                value=st.session_state.constraints["max_budget"],
                step=1000.0
            )
            
            availability = st.select_slider(
                "Required Availability",
                options=["99%", "99.9%", "99.99%", "99.999%"],
                value=st.session_state.constraints["availability"]
            )
            
            compliance = st.multiselect(
                "Compliance Requirements",
                ["HIPAA", "GDPR", "PCI-DSS", "SOC2", "ISO27001"],
                default=st.session_state.constraints["compliance"]
            )
            
            risk_tolerance = st.select_slider(
                "Risk Tolerance",
                options=["low", "medium", "high"],
                value=st.session_state.constraints["risk_tolerance"]
            )
            
            optimization_goals = st.multiselect(
                "Optimization Goals",
                [g.value for g in OptimizationGoal],
                default=st.session_state.constraints["optimization_goals"]
            )
            
            if st.form_submit_button("Save Constraints"):
                st.session_state.constraints = {
                    "max_budget": max_budget,
                    "availability": availability,
                    "compliance": compliance,
                    "risk_tolerance": risk_tolerance,
                    "optimization_goals": optimization_goals
                }
                st.success("Constraints saved!")
    
    # Display current resources
    if st.session_state.resources:
        st.markdown("---")
        st.subheader("📋 Current Infrastructure")
        
        df = pd.DataFrame(st.session_state.resources)
        
        # Metrics row
        metric_col1, metric_col2, metric_col3, metric_col4 = st.columns(4)
        with metric_col1:
            st.metric("Total Resources", len(df))
        with metric_col2:
            total_cost = df['monthly_cost'].sum()
            st.metric("Total Monthly Cost", f"${total_cost:,.2f}")
        with metric_col3:
            avg_cost = df['monthly_cost'].mean()
            st.metric("Avg Cost/Resource", f"${avg_cost:,.2f}")
        with metric_col4:
            providers = df['provider'].nunique()
            st.metric("Cloud Providers", providers)
        
        # Resource table
        st.dataframe(
            df[['name', 'provider', 'instance_type', 'region', 'quantity', 
                'monthly_cost', 'usage_pattern', 'criticality']],
            use_container_width=True
        )
        
        # Cost visualization
        fig = px.bar(
            df, 
            x='name', 
            y='monthly_cost', 
            color='provider',
            title="Monthly Costs by Resource",
            labels={'monthly_cost': 'Cost ($)', 'name': 'Resource'}
        )
        st.plotly_chart(fig, use_container_width=True)
        
        # Run analysis button
        col_btn1, col_btn2, col_btn3 = st.columns([1, 2, 1])
        with col_btn2:
            analysis_disabled = st.session_state.get('operation_in_progress', False)
            if st.button("🚀 Run Optimization Analysis", type="primary", use_container_width=True, disabled=analysis_disabled):
                st.session_state.operation_in_progress = True
                
                # AUTO-INITIALIZE AGENT IF NEEDED
                if not st.session_state.api_mode and not st.session_state.agent:
                    with st.spinner("Auto-initializing agent..."):
                        try:
                            env_openai = os.getenv("OPENAI_API_KEY")
                            env_aws_key = os.getenv("AWS_ACCESS_KEY_ID")
                            env_aws_secret = os.getenv("AWS_SECRET_ACCESS_KEY")
                            env_azure = os.getenv("AZURE_SUBSCRIPTION_KEY")
                            env_gcp = os.getenv("GCP_CREDENTIALS_PATH")
                            
                            aws_creds = None
                            if env_aws_key and env_aws_secret:
                                aws_creds = {
                                    'aws_access_key_id': env_aws_key,
                                    'aws_secret_access_key': env_aws_secret
                                }
                            
                            azure_creds = None
                            if env_azure:
                                azure_creds = {'subscription_key': env_azure}
                            
                            gcp_creds = None
                            if env_gcp:
                                gcp_creds = {'credentials_path': env_gcp}
                            
                            openai_key = env_openai if st.session_state.use_llm else None
                            
                            st.session_state.agent = CloudRationalizationAgent(
                                openai_api_key=openai_key,
                                aws_credentials=aws_creds,
                                azure_credentials=azure_creds,
                                gcp_credentials=gcp_creds
                            )
                            
                            st.session_state.creds = {
                                'aws': bool(aws_creds),
                                'azure': bool(azure_creds),
                                'gcp': bool(gcp_creds),
                                'openai': bool(openai_key)
                            }
                            
                            st.success("✅ Agent auto-initialized")
                        except Exception as e:
                            st.error(f"Failed to auto-initialize agent: {e}")
                            st.session_state.operation_in_progress = False
                            st.stop()
                
                if st.session_state.api_mode:
                    # API Mode
                    with st.spinner("Calling API for analysis..."):
                        try:
                            resources_data = []
                            for r in st.session_state.resources:
                                resources_data.append({
                                    "name": r['name'],
                                    "resource_type": r['resource_type'],
                                    "provider": r['provider'],
                                    "region": r['region'],
                                    "specifications": r['specifications'],
                                    "quantity": r['quantity'],
                                    "usage_pattern": r['usage_pattern'],
                                    "monthly_cost": r['monthly_cost'],
                                    "fault_tolerant": r['fault_tolerant']
                                })
                            # CRITICAL FIX: Read current mode from sidebar and pass to API
                            use_llm = st.session_state.get('use_llm', False)  # True for LLM Mode, False for Tool Mode                            
                            # Make API call with mode parameter
                            response = requests.post(
                                f"{st.session_state.api_url}/analyze",
                                params={"use_llm": use_llm},  # Pass mode as query parameter
                                json={
                                    "current_infrastructure": resources_data,
                                    "business_constraints": st.session_state.constraints,
                                    "optimization_goals": st.session_state.constraints["optimization_goals"],
                                    "time_horizon": "1 year"
                                },
                                timeout=30
                            )
                            
                            if response.status_code == 200:
                                st.session_state.analysis_result = response.json()
                                st.success("Analysis complete! Check the Analysis Results tab.")
                            else:
                                error_msg = response.text
                                st.error(f"API error: {response.status_code}")
                                if "quota" in error_msg.lower() or "429" in error_msg:
                                    st.warning("⚠️ API quota exceeded. The server may be rate-limited.")
                                
                        except requests.exceptions.Timeout:
                            st.error("API request timed out after 30 seconds")
                        except Exception as e:
                            st.error(f"Error: {e}")
                        finally:
                            st.session_state.operation_in_progress = False
                
                else:
                    # Local Agent Mode
                    if st.session_state.agent:
                        with st.spinner("Analyzing infrastructure..."):
                            try:
                                # Convert to Pydantic models (your existing code)
                                resources = []
                                for r in st.session_state.resources:
                                    resources.append(CloudResource(
                                        name=r['name'],
                                        resource_type=r['resource_type'],
                                        provider=r['provider'],
                                        region=r['region'],
                                        specifications=r['specifications'],
                                        quantity=r['quantity'],
                                        usage_pattern=r['usage_pattern'],
                                        monthly_cost=r['monthly_cost'],
                                        fault_tolerant=r['fault_tolerant']
                                    ))
                                
                                total_cost = sum(r.monthly_cost for r in resources)
                                
                                constraints = BusinessConstraints(
                                    max_budget=st.session_state.constraints["max_budget"],
                                    min_availability=st.session_state.constraints["availability"],
                                    compliance_requirements=st.session_state.constraints["compliance"],
                                    risk_tolerance=st.session_state.constraints["risk_tolerance"]
                                )
                                
                                goals = [OptimizationGoal(g) for g in st.session_state.constraints["optimization_goals"]]
                                
                                request = RationalizationRequest(
                                    current_infrastructure=resources,
                                    business_constraints=constraints,
                                    optimization_goals=goals,
                                    time_horizon="1 year"
                                )
                                
                                # Run analysis
                                result = run_analysis_sync(st.session_state.agent, request)
                                
                                # Check if we need to show demo analysis
                                show_demo = False
                                error_message = None
                                error_type = None
                                
                                if isinstance(result, dict):
                                    # Check for specific error modes
                                    if result.get('mode') in ['quota_error', 'quota_cached', 'connection_error', 'timeout_error', 'error_fallback']:
                                        show_demo = result.get('show_demo', False)
                                        error_message = result.get('analysis', 'Analysis error occurred')
                                        error_type = result.get('mode', 'unknown')
                                        
                                        # Show appropriate error message
                                        if error_type == 'connection_error':
                                            st.error("🌐 Network Connection Error")
                                            st.markdown(error_message)  # Shows the detailed help
                                        elif error_type == 'quota_error' or error_type == 'quota_cached':
                                            st.error("💰 OpenAI Quota Exceeded")
                                            st.markdown(error_message)
                                        elif error_type == 'timeout_error':
                                            st.error("⏱️ Analysis Timeout")
                                            st.markdown(error_message)
                                        else:
                                            st.error("⚠️ Analysis Warning")
                                            st.info(error_message)
                                        
                                        # Generate demo analysis
                                        demo_result = {
                                            "summary": {
                                                "current_cost": total_cost,
                                                "optimized_cost": total_cost * 0.7,
                                                "savings": total_cost * 0.3,
                                                "savings_percentage": 30
                                            },
                                            "analysis": f"""## 📊 Demo Analysis

            ### Current Infrastructure
            - **Total Resources:** {len(resources)}
            - **Monthly Cost:** ${total_cost:,.2f}

            ### Recommendations
            1. **Right-size over-provisioned instances**
            - Savings: ${total_cost * 0.15:,.2f}/month
            - Risk: Low

            2. **Purchase Reserved Instances**
            - Savings: ${total_cost * 0.25:,.2f}/month  
            - Risk: Medium

            3. **Use Spot Instances**
            - Savings: ${total_cost * 0.10:,.2f}/month
            - Risk: High

            ### Estimated Total Savings
            - **Monthly:** ${total_cost * 0.3:,.2f}
            - **Annual:** ${total_cost * 0.3 * 12:,.2f}
            """,
                                            "recommendations": [
                                                {"title": "Right-size instances", "savings": total_cost * 0.15, "risk": "low"},
                                                {"title": "Reserved Instances", "savings": total_cost * 0.25, "risk": "medium"},
                                                {"title": "Spot Instances", "savings": total_cost * 0.10, "risk": "high"}
                                            ],
                                            "mode": "demo_analysis",
                                            "error_type": error_type
                                        }
                                        
                                        st.session_state.analysis_result = demo_result
                                        st.success("✅ Demo analysis generated! Check the Analysis Results tab.")
                                        
                                    elif 'error' in result:
                                        st.error(f"Error: {result['error']}")
                                    else:
                                        # Normal successful result
                                        st.session_state.analysis_result = safe_serialize(result)
                                        st.success("✅ Analysis complete! Check the Analysis Results tab.")
                                else:
                                    st.session_state.analysis_result = safe_serialize(result)
                                    st.success("✅ Analysis complete! Check the Analysis Results tab.")
                                
                            except Exception as e:
                                st.error(f"Analysis error: {e}")
                                import traceback
                                st.code(traceback.format_exc())
                            finally:
                                st.session_state.operation_in_progress = False
                    else:
                        st.warning("Please initialize the agent first in the sidebar")
                        st.session_state.operation_in_progress = False
# ===== TAB 2: Price Comparison =====
with tab2:
    with tab2:
        st.subheader("💰 Multi-Cloud Price Comparison")
        
        with st.expander("⚙️ Comparison Settings", expanded=True):
            col1, col2 = st.columns(2)
            
            with col1:
                # Resource Category
                resource_category = st.selectbox(
                    "Resource Category",
                    ["Compute", "Database", "Storage", "Networking", "Containers", "Serverless"],
                    key="resource_category"
                )
                
                # Resource Type based on category
                if resource_category == "Compute":
                    resource_options = ["ec2", "vm", "compute"]
                elif resource_category == "Database":
                    resource_options = ["rds", "azure sql", "cloud sql"]
                elif resource_category == "Storage":
                    resource_options = ["s3", "blob", "cloud storage"]
                else:
                    resource_options = ["generic"]
                
                compare_resource = st.selectbox(
                    "Resource Type",
                    resource_options,
                    key="compare_resource"
                )
                
                # Instance Family
                instance_family = st.selectbox(
                    "Instance Family",
                    ["General Purpose", "Compute Optimized", "Memory Optimized", "GPU"],
                    key="instance_family"
                )
            
            with col2:
                # Region with friendly names
                region_map = {
                    "US East (N. Virginia)": "us-east-1",
                    "US West (Oregon)": "us-west-2",
                    "EU (Ireland)": "eu-west-1",
                    "Asia Pacific (Singapore)": "ap-southeast-1",
                    "Asia Pacific (Tokyo)": "ap-northeast-1",
                }
                selected_region = st.selectbox("Region", list(region_map.keys()))
                compare_region = region_map[selected_region]
                
                # Operating System
                os_type = st.selectbox(
                    "Operating System",
                    ["Linux", "Windows", "RHEL", "SUSE"],
                    key="os_type"
                )
                
                # Pricing Model
                pricing_model = st.selectbox(
                    "Pricing Model",
                    ["On-Demand", "1-Year Reserved", "3-Year Reserved", "Spot"],
                    key="pricing_model"
                )
            
            # Instance Type (dynamic based on family)
            if instance_family == "General Purpose":
                instance_options = ["t3.micro", "t3.medium", "t3.large", "m5.large", "m5.xlarge"]
            elif instance_family == "Compute Optimized":
                instance_options = ["c5.large", "c5.xlarge", "c5.2xlarge", "c6g.large"]
            elif instance_family == "Memory Optimized":
                instance_options = ["r5.large", "r5.xlarge", "r5.2xlarge", "x1e.xlarge"]
            else:  # GPU
                instance_options = ["g4dn.xlarge", "g4dn.2xlarge", "p3.2xlarge", "p4d.24xlarge"]
        
        compare_instance = st.selectbox("Instance Type", instance_options, key="compare_instance")
        
        # Quantity
        quantity = st.number_input("Number of Instances", min_value=1, value=1, step=1)
    
    # if st.button("Compare Prices", type="primary", use_container_width=True):
    #     with st.spinner("Fetching prices from all providers..."):
        compare_disabled = st.session_state.get('operation_in_progress', False)
        if st.button("Compare Prices", type="primary", use_container_width=True, disabled=compare_disabled):
            st.session_state.operation_in_progress = True
            
            with st.spinner("Fetching prices from all providers..."):
                if st.session_state.api_mode:
                    # API Mode
                    try:
                        response = requests.post(
                            f"{st.session_state.api_url}/compare-prices",
                            json={
                                "resource_type": compare_resource,
                                "specifications": {
                                    "instance_type": compare_instance,
                                    "os": "Linux"
                                },
                                "regions": [compare_region]
                            },
                            timeout=30
                        )
                        
                        if response.status_code == 200:
                            render_enhanced_pricing_dashboard(response)
                        else:
                            st.error(f"API error: {response.status_code}")
                            st.json(response.text)
                            
                    except requests.exceptions.Timeout:
                        st.error("Price comparison timed out after 30 seconds")
                    except Exception as e:
                        st.error(f"Error: {e}")
                    finally:
                        st.session_state.operation_in_progress = False
                
                else:
                    # Local Agent Mode - AUTO-INITIALIZE IF NEEDED
                    if not st.session_state.agent:
                        with st.spinner("Auto-initializing agent..."):
                            try:
                                env_openai = os.getenv("OPENAI_API_KEY")
                                env_aws_key = os.getenv("AWS_ACCESS_KEY_ID")
                                env_aws_secret = os.getenv("AWS_SECRET_ACCESS_KEY")
                                
                                aws_creds = None
                                if env_aws_key and env_aws_secret:
                                    aws_creds = {
                                        'aws_access_key_id': env_aws_key,
                                        'aws_secret_access_key': env_aws_secret
                                    }
                                
                                st.session_state.agent = CloudRationalizationAgent(
                                    openai_api_key=env_openai if st.session_state.use_llm else None,
                                    aws_credentials=aws_creds
                                )
                                st.success("✅ Agent auto-initialized")
                            except Exception as e:
                                st.error(f"Failed to auto-initialize: {e}")
                                st.session_state.operation_in_progress = False
                                st.stop()
                    
                    if st.session_state.agent:
                        try:
                            # Run comparison with timeout
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)
                            
                            try:
                                # Run in thread to avoid blocking
                                task = asyncio.ensure_future(
                                    asyncio.to_thread(
                                        st.session_state.agent.compare_prices,
                                        specifications={"instance_type": compare_instance, "os": "Linux"},
                                        regions=[compare_region]
                                    ),
                                    loop=loop
                                )
                                prices = loop.run_until_complete(
                                    asyncio.wait_for(task, timeout=30)
                                )
                            except asyncio.TimeoutError:
                                st.error("Price comparison timed out after 30 seconds")
                                prices = None
                            finally:
                                loop.close()
                            
                            if prices:
                                # Create a mock response object
                                class MockResponse:
                                    def __init__(self, data):
                                        self.status_code = 200
                                        self._data = data
                                    def json(self):
                                        return self._data
                                
                                mock_response = MockResponse(prices)
                                render_enhanced_pricing_dashboard(mock_response)
                            
                        except Exception as e:
                            st.error(f"Agent error: {e}")
                        finally:
                            st.session_state.operation_in_progress = False
                    else:
                        st.warning("Agent initialization failed")
                        st.session_state.operation_in_progress = False

# ===== TAB 3: Analysis Results =====
with tab3:
    if st.session_state.analysis_result:
        result = st.session_state.analysis_result
        
        st.subheader("📊 Optimization Results")
        
        # ===== ENHANCED SUMMARY SECTION =====
        # ===== ENHANCED SUMMARY SECTION =====
        if 'summary' in result:
            summary = result['summary']
            
            # FIX: Get total resources from session state, not just result
            total_resources = len(st.session_state.resources)
            
            # Top metrics row
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric(
                    "Total Resources",
                    total_resources  # ← FIXED: Always shows correct count
                )
            
            with col2:
                current_cost = summary.get('current_cost', 0)
                if current_cost == 0 and st.session_state.resources:
                    # Calculate from session state if not in result
                    current_cost = sum(r.get('monthly_cost', 0) for r in st.session_state.resources)
                
                st.metric(
                    "Current Monthly",
                    f"${current_cost:,.2f}"
                )
            
            with col3:
                optimized_cost = summary.get('optimized_cost', current_cost * 0.7)
                savings = summary.get('savings', summary.get('total_savings', current_cost - optimized_cost))
                
                st.metric(
                    "Optimized Monthly",
                    f"${optimized_cost:,.2f}",
                    delta=f"-${savings:,.2f}" if savings > 0 else None
                )
            
            with col4:
                savings_pct = summary.get('savings_percentage', 0)
                if savings_pct == 0 and current_cost > 0:
                    savings_pct = round((savings / current_cost * 100), 1)
                
                st.metric(
                    "Savings %",
                    f"{savings_pct}%",
                    delta_color="inverse"
                )
            
            # ===== RESOURCES BY TYPE (New) =====
            if 'resources_by_type' in summary:
                st.markdown("### 📋 Resources by Type")
                type_data = summary['resources_by_type']
                
                # Create columns dynamically based on number of types
                types = list(type_data.keys())
                cols = st.columns(len(types))
                
                for i, (resource_type, count) in enumerate(type_data.items()):
                    with cols[i]:
                        st.info(f"**{resource_type.upper()}**\n\n{count}")
            
            # ===== CONSTRAINTS APPLIED (New) =====
            if 'constraints_applied' in summary:
                with st.expander("📋 Applied Business Constraints"):
                    constraints = summary['constraints_applied']
                    st.json(constraints)
            
            # ===== BUDGET ALERT (New) =====
            if 'budget_alert' in result:
                budget = result['budget_alert']
                st.error(f"⚠️ **{budget['title']}**")
                st.markdown(f"{budget['description']}")
                st.markdown(f"**Required Savings:** ${budget['savings']:,.2f}")
        
        else:
            # Fallback to old summary format
            if st.session_state.resources:
                current_cost = sum(r.get('monthly_cost', 0) for r in st.session_state.resources)
            else:
                current_cost = result.get('summary', {}).get('current_cost', 0)
            
            optimized_cost = result.get('summary', {}).get('optimized_cost', current_cost * 0.7)
            savings = current_cost - optimized_cost
            savings_pct = (savings / current_cost * 100) if current_cost > 0 else 0
            
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Current Monthly", f"${current_cost:,.2f}")
            with col2:
                st.metric("Optimized", f"${optimized_cost:,.2f}", delta=f"-${savings:,.2f}")
            with col3:
                st.metric("Monthly Savings", f"${savings:,.2f}", delta=f"{savings_pct:.1f}%")
            with col4:
                st.metric("Annual Savings", f"${savings * 12:,.2f}")
        
        # ===== ANALYSIS TEXT =====
        if 'analysis' in result:
            st.markdown("### 📝 Detailed Analysis")
            st.markdown(result['analysis'])
        
        # ===== RECOMMENDATIONS =====
        if 'recommendations' in result:
            st.markdown("### ✅ Key Recommendations")
            
            # Show savings summary
            total_savings = sum(r.get('savings', 0) for r in result['recommendations'])
            st.success(f"💰 **Total Potential Savings: ${total_savings:,.2f}/month**")
            
            for i, rec in enumerate(result['recommendations'], 1):
                if rec.get('savings', 0) > 0:
                    risk_class = f"risk-{rec.get('risk', 'medium')}"
                    st.markdown(f"""
                    <div class='recommendation-card'>
                        <h4>{i}. {rec.get('title', 'Recommendation')}</h4>
                        <p>{rec.get('description', rec.get('reason', ''))}</p>
                        <p><span class='savings-positive'>💰 Savings: ${rec.get('savings', 0):,.2f}/month</span></p>
                        <p>Risk: <span class='{risk_class}'>{rec.get('risk', 'MEDIUM').upper()}</span> | Effort: {rec.get('effort', 'MEDIUM').upper()}</p>
                        <p><small>{rec.get('reasoning', '')}</small></p>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    # Monitoring recommendations (no savings)
                    st.markdown(f"""
                    <div class='recommendation-card' style='border-left-color: #999;'>
                        <h4>{i}. {rec.get('title', 'Recommendation')}</h4>
                        <p>{rec.get('description', rec.get('reason', ''))}</p>
                        <p><span>ℹ️ No immediate savings identified</span></p>
                        <p><small>{rec.get('reasoning', '')}</small></p>
                    </div>
                    """, unsafe_allow_html=True)
        
        # ===== SKIPPED RESOURCES (New) =====
        if 'skipped_resources' in result:
            with st.expander("📌 Resources with No Recommendations"):
                for skipped in result['skipped_resources']:
                    st.markdown(f"- **{skipped.get('name')}** ({skipped.get('type')}): {skipped.get('reason', 'No reason provided')}")
        
        # ===== IMPLEMENTATION TIMELINE =====
        if 'timeline' in result:
            st.markdown("### 📅 Implementation Timeline")
            st.dataframe(pd.DataFrame(result['timeline']), use_container_width=True)
        
        # ===== EXPORT RESULTS =====
        st.markdown("### 📥 Export Results")
        col_exp1, col_exp2 = st.columns(2)
        
        with col_exp1:
            # JSON Export
            json_str = json.dumps(result, indent=2, default=str)
            st.download_button(
                label="📥 Download as JSON",
                data=json_str,
                file_name=f"analysis_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                mime="application/json",
                use_container_width=True
            )
        
        with col_exp2:
            # CSV Export (recommendations only)
            if 'recommendations' in result:
                import pandas as pd
                df = pd.DataFrame(result['recommendations'])
                csv_data = df.to_csv(index=False)
                st.download_button(
                    label="📥 Download Recommendations CSV",
                    data=csv_data,
                    file_name=f"recommendations_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
    
    else:
        st.info("Run an optimization analysis first to see results here.")
        
        if st.button("Run Demo Analysis", use_container_width=True):
            if st.session_state.resources:
                # Create demo analysis with enhanced format
                total = sum(r['monthly_cost'] for r in st.session_state.resources)
                
                # Count by type
                types = {}
                for r in st.session_state.resources:
                    r_type = r.get('resource_type', 'compute')
                    types[r_type] = types.get(r_type, 0) + 1
                
                st.session_state.analysis_result = {
                    "summary": {
                        "total_resources": len(st.session_state.resources),
                        "resources_by_type": types,
                        "current_cost": total,
                        "optimized_cost": total * 0.7,
                        "total_savings": total * 0.3,
                        "savings_percentage": 30,
                        "constraints_applied": {
                            "risk_tolerance": "medium",
                            "max_budget": "unlimited",
                            "min_availability": "99.9%"
                        }
                    },
                    "analysis": "## Demo Analysis\n\nThis is a sample analysis showing what your results would look like.",
                    "recommendations": [
                        {
                            "title": "Right-size over-provisioned instances",
                            "description": "Consider downsizing instances with low utilization",
                            "savings": total * 0.15,
                            "risk": "low",
                            "effort": "low",
                            "reasoning": "Based on typical utilization patterns"
                        },
                        {
                            "title": "Purchase Reserved Instances",
                            "description": "For steady-state production workloads",
                            "savings": total * 0.25,
                            "risk": "medium",
                            "effort": "medium",
                            "reasoning": "1-year commitment yields 40% savings"
                        }
                    ]
                }
                st.success("Demo analysis generated!")
                st.rerun()

# ===== TAB 4: Reports =====
with tab4:
    st.subheader("📊 Generate Reports")
    
    if not st.session_state.analysis_result:
        st.info("ℹ️ Run an optimization analysis first to generate reports")
    else:
        result = st.session_state.analysis_result
        
        # Report type selector
        report_type = st.selectbox(
            "Report Type",
            ["Executive Summary", "Detailed Technical Report", "Cost Savings Analysis", "Migration Plan"],
            key="report_type_selector"
        )
        
        # Preview of report based on type
        st.markdown("### 👓 Preview")
        
        if report_type == "Executive Summary":
            st.markdown("""
            **Executive Summary** - High-level overview for stakeholders
            - Key findings and recommendations
            - Total savings potential
            - Implementation timeline
            """)
        elif report_type == "Detailed Technical Report":
            st.markdown("""
            **Technical Report** - Detailed analysis for engineers
            - Resource-by-resource breakdown
            - Technical implementation steps
            - Risk assessments
            """)
        elif report_type == "Cost Savings Analysis":
            st.markdown("""
            **Savings Analysis** - Financial focus
            - Monthly and annual savings
            - ROI calculations
            - Payback periods
            """)
        else:  # Migration Plan
            st.markdown("""
            **Migration Plan** - Step-by-step guide
            - Migration phases
            - Timeline estimates
            - Resource dependencies
            """)
        
        st.markdown("---")
        st.subheader("📥 Download Options")
        
        # Create different report formats based on selected type
        col1, col2 = st.columns(2)
        
        # Get common data
        current_cost = result.get('summary', {}).get('current_cost', 0)
        optimized_cost = result.get('summary', {}).get('optimized_cost', 0)
        savings = result.get('summary', {}).get('savings', 0)
        savings_pct = result.get('summary', {}).get('savings_percentage', 0)
        recommendations = result.get('recommendations', [])
        
        # Generate report content based on type
        if report_type == "Executive Summary":
            report_intro = "## Executive Summary\nHigh-level overview for stakeholders\n\n"
            report_content = f"""
**Key Findings**
- Current monthly spend: ${current_cost:,.2f}
- Optimization potential: ${savings:,.2f}/month ({savings_pct:.1f}%)
- Payback period: 8 months

**Top Recommendations**
"""
            for i, rec in enumerate(recommendations[:3], 1):
                report_content += f"{i}. {rec.get('title', 'Recommendation')} - Save ${rec.get('savings', 0):,.2f}\n"
            
        elif report_type == "Detailed Technical Report":
            report_intro = "## Detailed Technical Report\nFor engineering team\n\n"
            report_content = f"""
**Resource Analysis**
Total Resources: {len(st.session_state.resources)}

**Technical Implementation Steps**
"""
            for i, rec in enumerate(recommendations, 1):
                report_content += f"""
{i}. {rec.get('title', 'Recommendation')}
   • Implementation: {rec.get('description', rec.get('reason', 'See details'))}
   • Risk Level: {rec.get('risk', 'medium').upper()}
   • Expected Savings: ${rec.get('savings', 0):,.2f}
"""
            
        elif report_type == "Cost Savings Analysis":
            report_intro = "## Cost Savings Analysis\nFinancial impact assessment\n\n"
            report_content = f"""
**Savings Summary**
Monthly Savings: ${savings:,.2f}
Annual Savings: ${savings * 12:,.2f}
Savings Percentage: {savings_pct:.1f}%

**ROI Analysis**
Payback Period: 8 months
5-Year Projected Savings: ${savings * 12 * 5:,.2f}
"""
            
        else:  # Migration Plan
            report_intro = "## Migration Plan\nStep-by-step guide\n\n"
            report_content = f"""
**Migration Phases**

Phase 1 - Quick Wins (Week 1-2)
"""
            for i, rec in enumerate(recommendations[:2], 1):
                report_content += f"• {rec.get('title', 'Recommendation')}\n"
            
            report_content += """
Phase 2 - Medium-term (Month 1-2)
• Purchase Reserved Instances
• Configure Auto-scaling

Phase 3 - Long-term (Month 3-6)
• Multi-cloud strategy
• Complete migration
"""
        
        with col1:
            # JSON Download - Raw data (same for all types)
            report_json = json.dumps(result, indent=2)
            st.download_button(
                label="📥 Download as JSON (Raw Data)",
                data=report_json,
                file_name=f"cloud_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                mime="application/json",
                key="download_json",
                use_container_width=True
            )
            
            # Markdown Download - Type-specific
            md_report = f"""# Cloud Optimization Report
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Report Type: {report_type}

{report_intro}
{report_content}
"""
            st.download_button(
                label=f"📥 Download as Markdown ({report_type})",
                data=md_report,
                file_name=f"cloud_report_{report_type.lower().replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
                mime="text/markdown",
                key="download_md",
                use_container_width=True
            )
        
        with col2:
            # Text Download - Type-specific
            txt_report = f"""CLOUD OPTIMIZATION REPORT
========================================
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Report Type: {report_type}
========================================

{report_intro.replace('#', '').strip()}
{report_content}
"""
            st.download_button(
                label=f"📥 Download as Text ({report_type})",
                data=txt_report,
                file_name=f"cloud_report_{report_type.lower().replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                mime="text/plain",
                key="download_txt",
                use_container_width=True
            )
            
            # CSV Download - Recommendations (same for all)
            if recommendations:
                import pandas as pd
                df = pd.DataFrame(recommendations)
                csv_data = df.to_csv(index=False)
                st.download_button(
                    label="📥 Download as CSV (Recommendations)",
                    data=csv_data,
                    file_name=f"recommendations_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv",
                    key="download_csv",
                    use_container_width=True
                )

with tab5:
    st.subheader("🏢 On-Prem to Cloud Migration Advisor")
    st.markdown("Analyze your on-premise infrastructure and get intelligent migration recommendations based on the 5 R's (Rehost, Replatform, Refactor, Retire, Retain)")
    
    # Initialize session state for on-prem resources
    if 'onprem_resources' not in st.session_state:
        st.session_state.onprem_resources = []
    
    if 'migration_analysis' not in st.session_state:
        st.session_state.migration_analysis = None
    
    # ===== MAIN LAYOUT =====
    col1, col2 = st.columns([2, 1])
    
    with col1:
        # ===== MANUAL ENTRY FORM =====
        st.markdown("### ➕ Add On-Premise Resource")
        
        with st.form("onprem_form"):
            st.markdown("**Basic Information**")
            row1_col1, row1_col2, row1_col3 = st.columns(3)
            
            with row1_col1:
                onprem_name = st.text_input("Server Name", value="server-01")
                application_name = st.text_input("Application Name", value="app-name")
            
            with row1_col2:
                app_tier = st.selectbox(
                    "Application Tier",
                    ["web", "app", "data", "cache", "batch", "storage"]
                )
                workload_type = st.selectbox(
                    "Workload Type",
                    ["Web Server", "Application Server", "Database", "Batch Processing", 
                     "File Server", "Cache", "Message Queue", "ETL Job"]
                )
            
            with row1_col3:
                business_criticality = st.select_slider(
                    "Business Criticality",
                    options=["low", "medium", "high"],
                    value="medium"
                )
                data_sensitivity = st.selectbox(
                    "Data Sensitivity",
                    ["public", "internal", "pii", "financial", "hipaa", "gdpr"]
                )
            
            st.markdown("**Hardware Specifications**")
            row2_col1, row2_col2, row2_col3 = st.columns(3)
            
            with row2_col1:
                cpu_cores = st.number_input("CPU Cores", min_value=1, value=8, step=2)
                cpu_util = st.slider("Avg CPU Utilization (%)", 0, 100, 30)
            
            with row2_col2:
                ram_gb = st.number_input("RAM (GB)", min_value=1, value=32, step=8)
                memory_util = st.slider("Avg Memory Utilization (%)", 0, 100, 40)
            
            with row2_col3:
                storage_gb = st.number_input("Storage (GB)", min_value=10, value=1000, step=100)
                storage_util = st.slider("Storage Utilization (%)", 0, 100, 50)
            
            st.markdown("**Software & Technology Stack**")
            row3_col1, row3_col2, row3_col3 = st.columns(3)
            
            with row3_col1:
                os_type = st.selectbox(
                    "Operating System",
                    ["Linux", "Windows Server", "RHEL", "Ubuntu", "CentOS", "Solaris", "AIX"]
                )
                database_type = st.text_input("Database (if applicable)", value="", 
                                             help="e.g., SQL Server 2016, Oracle 19c, PostgreSQL 13, MySQL 8")
            
            with row3_col2:
                middleware = st.text_input("Middleware/App Server", value="",
                                          help="e.g., IIS, Apache, Tomcat, WebLogic, WebSphere")
                integration_patterns = st.multiselect(
                    "Integration Patterns",
                    ["REST APIs", "SOAP", "Message Queues", "File Transfers", "JDBC/ODBC", "gRPC"]
                )
            
            with row3_col3:
                end_of_life = st.checkbox("OS/DB Approaching End of Life")
                fault_tolerant = st.checkbox("Requires High Availability")
                age_years = st.number_input("Server Age (years)", min_value=0, value=3)
            
            st.markdown("**Dependencies**")
            dependencies = st.text_input("Dependencies (comma-separated server names)", value="",
                                        help="e.g., db01, cache01, app02")
            
            submitted = st.form_submit_button("➕ Add On-Prem Resource", type="primary")
            
            if submitted:
                new_onprem = {
                    "server_name": onprem_name,
                    "application_name": application_name,
                    "app_tier": app_tier,
                    "workload_type": workload_type,
                    "cpu_cores": cpu_cores,
                    "ram_gb": ram_gb,
                    "storage_gb": storage_gb,
                    "os": os_type,
                    "database_type": database_type,
                    "middleware": middleware,
                    "integration_patterns": integration_patterns,
                    "data_sensitivity": data_sensitivity,
                    "business_criticality": business_criticality,
                    "age_years": age_years,
                    "end_of_life": end_of_life,
                    "cpu_utilization": cpu_util,
                    "memory_utilization": memory_util,
                    "storage_utilization": storage_util,
                    "fault_tolerant": fault_tolerant,
                    "dependencies": [d.strip() for d in dependencies.split(",") if d.strip()]
                }
                st.session_state.onprem_resources.append(new_onprem)
                st.success(f"✅ Added {onprem_name}")
        
        # ===== IMPORT SECTION - FIXED COLUMN MAPPING =====
        st.markdown("### 📤 Import On-Premise Inventory")
        with st.expander("📤 Import On-Premise Inventory", expanded=False):
            st.markdown("""
            **Supported formats:** CSV, Excel (.xlsx, .xls)
            
            **Required columns:**
            - `server_name` - Server name
            - `application_name` - Application name
            - `app_tier` - web/app/data/cache/batch/storage
            - `workload_type` - Type of workload
            - `cpu_cores` - Number of CPU cores
            - `ram_gb` - RAM in GB
            - `storage_gb` - Storage in GB
            - `os` - Operating system
            """)
            
            uploaded_file = st.file_uploader(
                "Choose inventory file",
                type=['csv', 'xlsx', 'xls'],
                key="onprem_uploader"
            )
            
            if uploaded_file is not None:
                try:
                    import pandas as pd
                    import numpy as np
                    
                    # Read file
                    if uploaded_file.name.endswith('.csv'):
                        df = pd.read_csv(uploaded_file)
                    else:
                        df = pd.read_excel(uploaded_file)
                    
                    # FIX: Clean column names - strip whitespace and standardize
                    #df.columns = df.columns.str.strip().str.lower().str.replace(' ', '_')
                    # Replace NaN with empty string
                    #df = df.fillna('')
                    
                    st.success(f"✅ File loaded: {len(df)} servers found")
                       
                    # Show preview
                    st.markdown("**Preview Data:**")
                    preview_df = st.dataframe(df.head(10))
                    
                    # Display with styled headers
                    # st.dataframe(
                    #     preview_df,
                    #     use_container_width=True,
                    #     hide_index=True
                    # )


                    # Column mapping
                    st.markdown("**Map Columns to Your File**")
                                
                    # Create column lists
                    all_columns = list(df.columns)
                    columns_with_na = ['Not in file'] + all_columns
                    
                    col1_map, col2_map, col3_map = st.columns(3)
                    
                    with col1_map:
                        name_col = st.selectbox(
                            "Server Name column",
                            all_columns,
                            index=_find_column_index_fixed(df, ['server_name', 'server', 'name', 'hostname'])
                        )
                        
                        app_name_col = st.selectbox(
                            "Application Name column",
                            all_columns,
                            index=_find_column_index_fixed(df, ['application_name', 'app', 'application'])
                        )
                        
                        tier_col = st.selectbox(
                            "App Tier column",
                            all_columns,
                            index=_find_column_index_fixed(df, ['app_tier', 'tier', 'layer'])
                        )
                    
                    with col2_map:
                        workload_col = st.selectbox(
                            "Workload Type column",
                            all_columns,
                            index=_find_column_index_fixed(df, ['workload_type', 'workload'])
                        )
                        
                        cpu_col = st.selectbox(
                            "CPU Cores column",
                            all_columns,
                            index=_find_column_index_fixed(df, ['cpu_cores', 'cpu', 'cores'])
                        )
                        
                        ram_col = st.selectbox(
                            "RAM (GB) column",
                            all_columns,
                            index=_find_column_index_fixed(df, ['ram_gb', 'ram', 'memory'])
                        )
                    
                    with col3_map:
                        storage_col = st.selectbox(
                            "Storage (GB) column",
                            all_columns,
                            index=_find_column_index_fixed(df, ['storage_gb', 'storage', 'disk'])
                        )
                        
                        os_col = st.selectbox(
                            "OS column",
                            all_columns,
                            index=_find_column_index_fixed(df, ['os', 'operating_system'])
                        )
                        
                        db_col = st.selectbox(
                            "Database Type (optional)",
                            columns_with_na,
                            index=_find_column_index_with_na(df, ['database_type', 'database', 'db'])
                        )
                    
                    # More optional columns
                    col4_map, col5_map, col6_map = st.columns(3)
                    
                    with col4_map:
                        criticality_col = st.selectbox(
                            "Criticality (optional)",
                            columns_with_na,
                            index=_find_column_index_with_na(df, ['business_criticality', 'criticality', 'critical'])
                        )
                        
                        sensitivity_col = st.selectbox(
                            "Data Sensitivity (optional)",
                            columns_with_na,
                            index=_find_column_index_with_na(df, ['data_sensitivity', 'sensitivity'])
                        )
                    
                    with col5_map:
                        cpu_util_col = st.selectbox(
                            "CPU Utilization % (optional)",
                            columns_with_na,
                            index=_find_column_index_with_na(df, ['cpu_utilization', 'cpu_util'])
                        )
                        
                        mem_util_col = st.selectbox(
                            "Memory Utilization % (optional)",
                            columns_with_na,
                            index=_find_column_index_with_na(df, ['memory_utilization', 'mem_util'])
                        )
                    
                    with col6_map:
                        fault_tolerant_col = st.selectbox(
                            "Fault Tolerant (optional)",
                            columns_with_na,
                            index=_find_column_index_with_na(df, ['fault_tolerant', 'ha_required'])
                        )
                        
                        age_col = st.selectbox(
                            "Age Years (optional)",
                            columns_with_na,
                            index=_find_column_index_with_na(df, ['age_years', 'age'])
                        )
                    
                    if st.button("📥 Import On-Prem Inventory", type="primary"):
                        imported_count = 0
                        errors = []
                        
                        for idx, row in df.iterrows():
                            try:
                                # Helper function to safely convert to string
                                def safe_str(val):
                                    if pd.isna(val) or val == '':
                                        return ''
                                    return str(val)
                                
                                # Helper function to safely convert to float
                                def safe_float(val, default=0.0):
                                    if pd.isna(val) or val == '':
                                        return default
                                    try:
                                        return float(val)
                                    except (ValueError, TypeError):
                                        return default
                                
                                # Helper function to safely convert to int
                                def safe_int(val, default=0):
                                    if pd.isna(val) or val == '':
                                        return default
                                    try:
                                        return int(float(val))
                                    except (ValueError, TypeError):
                                        return default
                                
                                # Required fields - always convert to appropriate types
                                server_name = safe_str(row[name_col])
                                app_name = safe_str(row[app_name_col])
                                app_tier = safe_str(row[tier_col]).lower()
                                workload = safe_str(row[workload_col])
                                
                                # Numeric fields with safe conversion
                                cpu = safe_int(row[cpu_col], 4)
                                ram = safe_float(row[ram_col], 16.0)
                                storage = safe_float(row[storage_col], 100.0)
                                os_type = safe_str(row[os_col])
                                
                                # Optional fields
                                db_type = ''
                                if db_col != 'Not in file':
                                    db_type = safe_str(row[db_col])
                                
                                criticality = 'medium'
                                if criticality_col != 'Not in file':
                                    criticality = safe_str(row[criticality_col]).lower()
                                    if criticality not in ['low', 'medium', 'high']:
                                        criticality = 'medium'
                                
                                sensitivity = 'internal'
                                if sensitivity_col != 'Not in file':
                                    sensitivity = safe_str(row[sensitivity_col]).lower()
                                
                                cpu_util = 30
                                if cpu_util_col != 'Not in file':
                                    cpu_util = safe_float(row[cpu_util_col], 30)
                                
                                mem_util = 40
                                if mem_util_col != 'Not in file':
                                    mem_util = safe_float(row[mem_util_col], 40)
                                
                                fault_tolerant = False
                                if fault_tolerant_col != 'Not in file':
                                    val = safe_str(row[fault_tolerant_col]).lower()
                                    fault_tolerant = val in ['true', 'yes', '1', 't', 'y', 'true']
                                
                                age_years = 3
                                if age_col != 'Not in file':
                                    age_years = safe_int(row[age_col], 3)
                                
                                # Create resource with all values properly typed
                                onprem_resource = {
                                    "server_name": server_name,
                                    "application_name": app_name,
                                    "app_tier": app_tier,
                                    "workload_type": workload,
                                    "cpu_cores": cpu,
                                    "ram_gb": ram,
                                    "storage_gb": storage,
                                    "os": os_type,
                                    "database_type": db_type,
                                    "business_criticality": criticality,
                                    "data_sensitivity": sensitivity,
                                    "cpu_utilization": cpu_util,
                                    "memory_utilization": mem_util,
                                    "fault_tolerant": fault_tolerant,
                                    "age_years": age_years,
                                    "middleware": '',
                                    "integration_patterns": [],
                                    "dependencies": []
                                }
                                
                                st.session_state.onprem_resources.append(onprem_resource)
                                imported_count += 1
                                
                            except Exception as e:
                                errors.append(f"Row {idx + 2}: {str(e)}")
                        
                        if imported_count > 0:
                            st.success(f"✅ Successfully imported {imported_count} on-prem servers!")
                        
                        if errors:
                            with st.expander(f"⚠️ {len(errors)} errors during import"):
                                for error in errors[:10]:
                                    st.error(error)
                
                except Exception as e:
                    st.error(f"Error reading file: {e}")    
    with col2:
        # ===== TARGET CLOUD SELECTION =====
        st.markdown("### ☁️ Target Cloud")
        target_cloud = st.selectbox(
            "Select Target Cloud Provider",
            ["AWS", "Azure", "GCP", "Multi-Cloud (All)"],
            key="target_cloud"
        )
        
        # ===== MIGRATION PREFERENCES =====
        st.markdown("### ⚙️ Migration Preferences")
        
        migration_priority = st.select_slider(
            "Migration Priority",
            options=["Cost Optimization", "Performance", "Lift & Shift", "Modernize"],
            value="Cost Optimization"
        )
        
        migration_timeline = st.selectbox(
            "Migration Timeline",
            ["Immediate (<3 months)", "3-6 months", "6-12 months", "12+ months", "Planning Phase"]
        )
        
        compliance_req = st.multiselect(
            "Compliance Requirements",
            ["SOC2", "HIPAA", "GDPR", "PCI-DSS", "ISO27001", "None"]
        )
        
        # ===== CURRENT INVENTORY STATS =====
        st.markdown("### 📊 Current Inventory")
        if st.session_state.onprem_resources:
            df_onprem = pd.DataFrame(st.session_state.onprem_resources)
            
            st.metric("Total Servers", len(df_onprem))
            
            # App count
            unique_apps = df_onprem['application_name'].nunique() if 'application_name' in df_onprem.columns else 0
            st.metric("Unique Applications", unique_apps)
            
            # Total resources
            total_cpu = df_onprem['cpu_cores'].sum()
            total_ram = df_onprem['ram_gb'].sum()
            total_storage = df_onprem['storage_gb'].sum()
            
            st.info(f"💰 **Total CPU Cores:** {total_cpu}")
            st.info(f"💾 **Total RAM:** {total_ram:,.0f} GB")
            st.info(f"📀 **Total Storage:** {total_storage:,.0f} GB")
        else:
            st.info("No on-prem resources added yet")
    
    # ===== DISPLAY CURRENT ON-PREM RESOURCES =====
    if st.session_state.onprem_resources:
        st.markdown("---")
        st.subheader("📋 On-Premise Infrastructure Inventory")
        
        df_display = pd.DataFrame(st.session_state.onprem_resources)
        
        # Show summary by application
        st.markdown("#### 📊 Inventory by Application")
        app_summary = df_display.groupby('application_name').agg({
            'server_name': 'count',
            'cpu_cores': 'sum',
            'ram_gb': 'sum',
            'storage_gb': 'sum'
        }).rename(columns={'server_name': 'server_count'})
        
        st.dataframe(app_summary, use_container_width=True)
        
        # Detailed table
        with st.expander("View Detailed Inventory"):
            st.dataframe(
                df_display[['server_name', 'application_name', 'app_tier', 'workload_type', 
                           'cpu_cores', 'ram_gb', 'storage_gb', 'os', 'database_type']],
                use_container_width=True
            )
        
        # ===== ANALYSIS BUTTONS =====
        col_btn1, col_btn2, col_btn3 = st.columns([1, 1, 1])
        
        with col_btn1:
            if st.button("🔧 Tool-Based Migration Analysis", use_container_width=True):
                with st.spinner("Analyzing on-prem to cloud mapping..."):
                    st.session_state.migration_analysis = analyze_onprem_migration_tool(
                        st.session_state.onprem_resources,
                        target_cloud,
                        migration_priority,
                        compliance_req,
                        migration_timeline
                    )
                    st.success("Migration analysis complete!")
        
        with col_btn2:
            llm_available = st.session_state.get('use_llm', False) and st.session_state.get('agent') and st.session_state.agent.llm
            if st.button("🧠 LLM-Based Migration Analysis", use_container_width=True, disabled=not llm_available):
                with st.spinner("AI analyzing migration strategies..."):
                    st.session_state.migration_analysis = analyze_onprem_migration_llm(
                        st.session_state.onprem_resources,
                        target_cloud,
                        migration_priority,
                        compliance_req,
                        st.session_state.agent
                    )
                    st.success("AI migration analysis complete!")
        
        with col_btn3:
            if st.button("🗑️ Clear All", use_container_width=True):
                st.session_state.onprem_resources = []
                st.session_state.migration_analysis = None
                st.rerun()
    
    # ===== DISPLAY MIGRATION ANALYSIS RESULTS =====
    if st.session_state.migration_analysis:
        st.markdown("---")
        st.subheader("📊 Migration Strategy Recommendations")
        
        analysis = st.session_state.migration_analysis
        
        # Summary cards
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric(
                "Total Servers",
                analysis['summary']['total_servers']
            )
        
        with col2:
            st.metric(
                "Est. Monthly Cloud Cost",
                f"${analysis['summary']['estimated_monthly_cost']:,.2f}"
            )
        
        with col3:
            st.metric(
                "Primary Strategy",
                analysis['summary']['primary_strategy']
            )
        
        with col4:
            complexity = analysis['summary'].get('complexity', 'Medium')
            color = "🟢" if complexity == "Low" else "🟡" if complexity == "Medium" else "🔴"
            st.metric(
                "Migration Complexity",
                f"{color} {complexity}"
            )
        
        # Strategy breakdown
        st.markdown("#### 📊 Strategy Breakdown (5 R's)")
        strategy_counts = analysis['summary']['strategy_breakdown']
        
        col_strat1, col_strat2, col_strat3, col_strat4, col_strat5 = st.columns(5)
        
        with col_strat1:
            st.info(f"**Rehost**\n\n{strategy_counts.get('Rehost', 0)} servers")
        with col_strat2:
            st.info(f"**Replatform**\n\n{strategy_counts.get('Replatform', 0)} servers")
        with col_strat3:
            st.warning(f"**Refactor**\n\n{strategy_counts.get('Refactor', 0)} servers")
        with col_strat4:
            st.error(f"**Retire**\n\n{strategy_counts.get('Retire', 0)} servers")
        with col_strat5:
            st.success(f"**Retain**\n\n{strategy_counts.get('Retain', 0)} servers")
        
        # Phased migration plan
        if 'migration_plan' in analysis:
            st.markdown("#### 📅 Phased Migration Plan")
            
            for phase in analysis['migration_plan']['phases']:
                st.markdown(f"""
                **{phase['phase']}** - {phase['timeline']}
                - {phase['description']}
                """)
        
        # Detailed recommendations by application
        st.markdown("#### 💡 Application-Level Recommendations")
        
        # Group by application
        app_recommendations = {}
        for rec in analysis['recommendations']:
            app_name = rec.get('application_name', 'Unknown')
            if app_name not in app_recommendations:
                app_recommendations[app_name] = []
            app_recommendations[app_name].append(rec)
        
        for app_name, app_recs in app_recommendations.items():
            with st.expander(f"📌 **{app_name}** - {len(app_recs)} servers"):
                for rec in app_recs:
                    col_rec1, col_rec2 = st.columns([1, 2])
                    
                    with col_rec1:
                        st.markdown(f"**Server:** `{rec['server_name']}`")
                        st.markdown(f"**Strategy:** `{rec['migration_strategy']}`")
                        st.markdown(f"**Target:** {rec['cloud_instance']}")
                        st.markdown(f"**Cost:** ${rec['monthly_cost']:,.2f}/mo")
                        st.markdown(f"**Confidence:** {rec['confidence']}%")
                    
                    with col_rec2:
                        st.markdown(f"**Rationale:** {rec['rationale']}")
                        st.markdown(f"**Next Steps :**")
                        for step in rec.get('next_steps', [])[:3]:
                            st.markdown(f"- {step}")
    
                    st.markdown("---")
    
    else:
        if st.session_state.onprem_resources:
            st.info("👆 Click an analysis button above to generate migration recommendations")
    
# ===== EXPORT SECTION FOR TAB 1 IMPORT=====
    if st.session_state.migration_analysis:
        st.markdown("---")
        st.subheader("📤 Export to Cloud Optimization (Tab 1)")
    
        with st.expander("Export Migration Recommendations as Cloud Resources", expanded=False):
            st.markdown("""
            **Export your migration recommendations to Tab 1 for cost optimization analysis**
            
            This will create a CSV file with all recommended cloud resources that can be imported 
            directly into **Tab 1 (Infrastructure Input)**. The export includes:
            
            - ✅ All resource types (compute, database, cache, storage, serverless, networking)
            - ✅ Correct instance types based on migration strategy
            - ✅ Estimated monthly costs
            - ✅ Usage patterns derived from workload types
            - ✅ Specifications (CPU, RAM, storage) preserved from on-prem
            """)
            
            analysis = st.session_state.migration_analysis
            
            # Helper function to map workload to usage pattern
            def get_usage_from_workload(workload):
                workload = str(workload).lower()
                if 'batch' in workload or 'etl' in workload:
                    return 'batch'
                elif 'web' in workload:
                    return 'variable'
                elif 'database' in workload:
                    return 'steady'
                else:
                    return 'steady'
            
            # Helper function to map migration strategy to resource type
            def get_resource_type_from_strategy(rec):
                strategy = rec['migration_strategy']
                workload = rec.get('workload_type', '').lower()
                app_tier = rec.get('app_tier', '').lower()
                db_type = rec.get('database_type', '').lower()
                middleware = rec.get('middleware', '').lower()
                
                if strategy == "Replatform":
                    if 'database' in workload or 'data' in app_tier or db_type:
                        return 'database'
                    elif 'cache' in app_tier or 'redis' in middleware:
                        return 'cache'
                    elif 'web' in app_tier or 'app' in app_tier:
                        return 'compute'  # PaaS still shows as compute in Tab 1
                    elif 'batch' in workload or 'etl' in workload:
                        return 'serverless'
                    elif 'file' in workload or 'storage' in app_tier:
                        return 'storage'
                    else:
                        return 'compute'
                
                elif strategy == "Refactor":
                    if 'web' in app_tier or 'app' in app_tier:
                        return 'serverless'
                    elif 'database' in workload:
                        return 'database'
                    elif 'cache' in app_tier:
                        return 'cache'
                    elif 'batch' in workload:
                        return 'serverless'
                    else:
                        return 'container'
                
                elif strategy == "Rehost":
                    return 'compute'
                
                else:  # Retire/Retain - not exported
                    return None
        
        # Build export data
        export_rows = []
        
        for rec in analysis['recommendations']:
            # Skip Retire and Retain
            if rec['migration_strategy'] in ['Retire', 'Retain']:
                continue
            
            # Get resource type
            resource_type = get_resource_type_from_strategy(rec)
            if not resource_type:
                continue
            
            # Get on-prem specs
            onprem_specs = rec.get('onprem_specs', {})
            
            # Create export row
            export_row = {
                "name": f"{rec['server_name']}-{resource_type}",
                "provider": rec['cloud_provider'].split()[0] if 'Multi' in rec['cloud_provider'] else rec['cloud_provider'],
                "resource_type": resource_type,
                "instance_type": rec['cloud_instance'],
                "region": "us-east-1",  # Default region - user can change in Tab 1
                "monthly_cost": round(rec['monthly_cost'], 2),
                "quantity": 1,
                "usage_pattern": get_usage_from_workload(rec.get('workload_type', '')),
                "fault_tolerant": rec.get('fault_tolerant', False),
                "criticality": rec.get('business_criticality', 'medium'),
                "os": rec.get('os', 'Linux'),
                "cpu": onprem_specs.get('cpu', 2),
                "memory": onprem_specs.get('ram', 8),
                "storage": onprem_specs.get('storage', 100)
            }
            
            export_rows.append(export_row)
        
        if not export_rows:
            st.warning("No exportable resources found (all recommendations are Retire/Retain)")
        else:
            export_df = pd.DataFrame(export_rows)
            # Show summary
            st.success(f"✅ Ready to export {len(export_rows)} cloud resources")
            
            # Summary by resource type
            st.markdown("**📊 Export Summary:**")
            summary = export_df.groupby('resource_type').agg({
                'name': 'count',
                'monthly_cost': 'sum'
            }).rename(columns={'name': 'count', 'monthly_cost': 'monthly_cost'})
            
            col1, col2 = st.columns(2)
            with col1:
                st.dataframe(summary, use_container_width=True)
            with col2:
                total_cost = export_df['monthly_cost'].sum()
                st.metric("Total Estimated Monthly Cost", f"${total_cost:,.2f}")
                st.metric("Total Resources", len(export_rows))
                
        # Preview
        with st.expander("👁️ Preview Export Data"):
            st.dataframe(export_df.head(10), use_container_width=True, hide_index=True)
        
        # Export options
        col_exp1, col_exp2, col_exp3 = st.columns(3)
        
        with col_exp1:
            # CSV Export
            csv_data = export_df.to_csv(index=False)
            st.download_button(
                label="📥 Download CSV for Tab 1",
                data=csv_data,
                file_name=f"cloud_resources_from_migration_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
                use_container_width=True,
                type="primary"
            )
        
        with col_exp2:
            st.info("""
            **Next Steps:**
            1. Download this CSV
            2. Go to **Tab 1 (Infrastructure Input)**
            3. Click **"Import from CSV/Excel"**
            4. Upload this file
            5. Run **LLM or Tool analysis** for optimization
            """)
        
        with col_exp3:
            # Show sample of what will be imported
            st.success(f"""
            **Sample Resource:**
            {export_rows[0]['name']}
            Type: {export_rows[0]['resource_type']}
            Instance: {export_rows[0]['instance_type']}
            Cost: ${export_rows[0]['monthly_cost']}/month
            """)
        

# ===== MIGRATION REPORT SECTION =====
    if st.session_state.migration_analysis:
        st.markdown("---")
        st.subheader("📊 Migration Analysis Report")
        
        analysis = st.session_state.migration_analysis
        
        # Create tabs for different views
        report_tab1, report_tab2, report_tab3 = st.tabs(["📈 Charts", "📋 Summary", "📥 Download Report"])
        
        with report_tab1:
            col_chart1, col_chart2 = st.columns(2)
            
            with col_chart1:
                # Strategy distribution pie chart
                fig1 = create_migration_distribution_chart(analysis['summary']['strategy_breakdown'])
                st.pyplot(fig1)
                plt.close()
            
            with col_chart2:
                # Timeline feasibility chart (if available)
                if 'timeline_feasibility' in analysis['summary']:
                    fig2 = create_timeline_feasibility_chart(analysis['summary']['timeline_feasibility'])
                    st.pyplot(fig2)
                    plt.close()
                else:
                    st.info("Timeline feasibility data not available")
            
            # Cost comparison chart with savings
            cloud_cost = analysis['summary']['estimated_monthly_cost']
            fig3, monthly_savings, annual_savings = create_cost_comparison_chart(
                cloud_cost, 
                analysis['summary']['total_servers']
            )
            st.pyplot(fig3)
            plt.close()
            
            # Show savings metrics
            col_sav1, col_sav2, col_sav3 = st.columns(3)
            with col_sav1:
                st.metric("Monthly Cloud Cost", f"${cloud_cost:,.0f}")
            with col_sav2:
                st.metric("Monthly Savings vs On-Prem", f"${monthly_savings:,.0f}", 
                        delta=f"{(monthly_savings/(cloud_cost * 1.4))*100:.0f}%")
            with col_sav3:
                st.metric("Annual Savings", f"${annual_savings:,.0f}")
        
        with report_tab2:
            # Summary text
            st.markdown(f"""
            ### Migration Summary
            
            **Infrastructure Overview:**
            - Total Servers: {analysis['summary']['total_servers']}
            - Target Cloud: {target_cloud}
            - Migration Priority: {migration_priority}
            - Timeline: {migration_timeline}
            - Compliance Requirements: {', '.join(compliance_req) if compliance_req and 'None' not in compliance_req else 'None'}
            
            **Cost Analysis:**
            - Estimated Monthly Cloud Cost: ${analysis['summary']['estimated_monthly_cost']:,.2f}
            - Estimated Annual Cloud Cost: ${analysis['summary']['estimated_monthly_cost'] * 12:,.2f}
            
            **Strategy Breakdown:**
            """)
            
            for strategy, count in analysis['summary']['strategy_breakdown'].items():
                if count > 0:
                    percentage = (count / analysis['summary']['total_servers']) * 100
                    st.markdown(f"- **{strategy}**: {count} servers ({percentage:.1f}%)")
            
            if 'timeline_feasibility' in analysis['summary']:
                st.markdown(f"""
                **Timeline Feasibility:**
                {analysis['summary']['timeline_feasibility']['overall']}
                """)
        
        with report_tab3:
            st.markdown("### Download Migration Report")
            st.markdown("Generate a comprehensive PDF report with all migration analysis details.")
            
            col_dl1, col_dl2 = st.columns(2)
            
            with col_dl1:
                report_format = st.selectbox(
                    "Report Format",
                    ["PDF (Detailed)", "CSV (Raw Data)", "JSON (Developer)"]
                )
            
            with col_dl2:
                include_charts = st.checkbox("Include charts in report", value=True)
            
            if st.button("📥 Generate Migration Report", type="primary", use_container_width=True):
                with st.spinner("Generating report..."):
                    
                    if report_format == "PDF (Detailed)":
                        # Generate PDF
                        pdf_path = generate_migration_pdf_report(
                            analysis, target_cloud, migration_priority, 
                            migration_timeline, compliance_req,
                            include_charts
                        )
                        
                        with open(pdf_path, 'rb') as f:
                            pdf_data = f.read()
                        
                        st.download_button(
                            label="📥 Click to Download PDF Report",
                            data=pdf_data,
                            file_name=f"migration_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
                            mime="application/pdf",
                            use_container_width=True
                        )
                        
                        # Clean up temp file
                        import os
                        os.unlink(pdf_path)
                    
                    elif report_format == "CSV (Raw Data)":
                        # Generate CSV
                        import pandas as pd
                        df = pd.DataFrame(analysis['recommendations'])
                        csv_data = df.to_csv(index=False)
                        
                        st.download_button(
                            label="📥 Click to Download CSV",
                            data=csv_data,
                            file_name=f"migration_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                            mime="text/csv",
                            use_container_width=True
                        )
                    
                    else:  # JSON
                        json_data = json.dumps(analysis, indent=2)
                        st.download_button(
                            label="📥 Click to Download JSON",
                            data=json_data,
                            file_name=f"migration_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                            mime="application/json",
                            use_container_width=True
                        )