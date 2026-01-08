#!/usr/bin/env python3
"""
AI-Powered Review Analyzer
Uses Claude API to analyze accommodation reviews
"""

import os
import anthropic
from typing import List, Dict, Optional


class ReviewAnalyzer:
    """Analyze accommodation reviews using Claude API"""
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize ReviewAnalyzer
        
        Args:
            api_key: Anthropic API key (or use ANTHROPIC_API_KEY env var)
        """
        self.api_key = api_key or os.environ.get('ANTHROPIC_API_KEY')
        
        if not self.api_key:
            print("⚠️ WARNUNG: Kein Anthropic API Key gefunden!")
            print("   → Setze ANTHROPIC_API_KEY environment variable")
            print("   → Oder übergib api_key beim Initialisieren")
            self.client = None
        else:
            self.client = anthropic.Anthropic(api_key=self.api_key)
    
    def analyze_reviews(self, reviews: List[str], listing_title: str = "") -> Dict[str, any]:
        """
        Analyze reviews using Claude API
        
        Args:
            reviews: List of review texts
            listing_title: Title of the listing (optional)
        
        Returns:
            Dictionary with analysis results
        """
        if not self.client:
            return {
                "error": "Kein API Key",
                "summary": "Review-Analyse nicht verfügbar (kein API Key)"
            }
        
        if not reviews or len(reviews) == 0:
            return {
                "summary": "Keine Reviews verfügbar",
                "positive": [],
                "negative": [],
                "cleanliness": "N/A",
                "location": "N/A",
                "value": "N/A"
            }
        
        # Combine reviews (max 10)
        review_text = "\n\n---\n\n".join(reviews[:10])
        
        # Limit to ~3000 chars to save tokens
        if len(review_text) > 3000:
            review_text = review_text[:3000] + "..."
        
        prompt = f"""Analysiere diese Gästebewertungen für eine Unterkunft ({listing_title}).

REVIEWS:
{review_text}

Erstelle eine prägnante Zusammenfassung auf DEUTSCH mit:

1. **Positiv** (2-3 Stichpunkte): Was loben Gäste am meisten?
2. **Negativ** (1-2 Stichpunkte): Was wird kritisiert? (Falls nichts → "Keine nennenswerten Kritikpunkte")
3. **Sauberkeit**: Bewertung (Sehr gut / Gut / OK / Problematisch)
4. **Lage**: Bewertung (Ausgezeichnet / Gut / OK / Schlecht)
5. **Preis-Leistung**: Bewertung (Sehr gut / Gut / OK / Teuer)

Antworte NUR mit diesem JSON Format (ohne Markdown):
{{
  "positive": ["Punkt 1", "Punkt 2", "Punkt 3"],
  "negative": ["Punkt 1"],
  "cleanliness": "Sehr gut",
  "location": "Ausgezeichnet",
  "value": "Gut",
  "summary": "Kurze 1-Satz Zusammenfassung"
}}"""
        
        try:
            # Call Claude API
            message = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=500,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            # Extract response
            response_text = message.content[0].text.strip()
            
            # Try to parse as JSON
            import json
            
            # Remove markdown code blocks if present
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
                response_text = response_text.strip()
            
            analysis = json.loads(response_text)
            return analysis
            
        except Exception as e:
            print(f"⚠️ Fehler bei Review-Analyse: {e}")
            return {
                "error": str(e),
                "summary": "Review-Analyse fehlgeschlagen"
            }
    
    def format_analysis_html(self, analysis: Dict) -> str:
        """
        Format analysis results as HTML
        
        Args:
            analysis: Analysis results from analyze_reviews()
        
        Returns:
            HTML string
        """
        if "error" in analysis:
            return f'<div style="color: #999; font-style: italic;">{analysis.get("summary", "Keine Analyse")}</div>'
        
        html = '<div style="background: #f0f7ff; padding: 15px; border-radius: 8px; margin: 15px 0;">'
        html += '<h4 style="margin: 0 0 10px 0; color: #667eea;">🤖 AI Review-Analyse</h4>'
        
        # Summary
        if analysis.get('summary'):
            html += f'<p style="margin: 5px 0;"><strong>Zusammenfassung:</strong> {analysis["summary"]}</p>'
        
        # Positive
        if analysis.get('positive'):
            html += '<p style="margin: 10px 0 5px 0;"><strong>✅ Positiv:</strong></p><ul style="margin: 0;">'
            for point in analysis['positive']:
                html += f'<li>{point}</li>'
            html += '</ul>'
        
        # Negative
        if analysis.get('negative'):
            html += '<p style="margin: 10px 0 5px 0;"><strong>⚠️ Zu beachten:</strong></p><ul style="margin: 0;">'
            for point in analysis['negative']:
                html += f'<li>{point}</li>'
            html += '</ul>'
        
        # Ratings
        html += '<p style="margin: 10px 0 5px 0;"><strong>Bewertungen:</strong></p>'
        html += '<div style="display: flex; gap: 15px; flex-wrap: wrap;">'
        
        if analysis.get('cleanliness'):
            html += f'<span>🧹 Sauberkeit: <strong>{analysis["cleanliness"]}</strong></span>'
        if analysis.get('location'):
            html += f'<span>📍 Lage: <strong>{analysis["location"]}</strong></span>'
        if analysis.get('value'):
            html += f'<span>💰 Preis-Leistung: <strong>{analysis["value"]}</strong></span>'
        
        html += '</div></div>'
        
        return html


# Example usage
if __name__ == "__main__":
    # Test with sample reviews
    sample_reviews = [
        "Die Unterkunft war sehr sauber und gut gelegen. Der Host war super freundlich!",
        "Zentrale Lage, aber etwas laut durch Straßenverkehr. Sonst alles top.",
        "Perfekt für einen Kurztrip! Würde jederzeit wiederkommen."
    ]
    
    analyzer = ReviewAnalyzer()
    result = analyzer.analyze_reviews(sample_reviews, "Cozy Apartment in Paris")
    
    print("Analysis Result:")
    print(result)
    print("\nHTML:")
    print(analyzer.format_analysis_html(result))
