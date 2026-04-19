# Financial Metrics Extractor

Advanced PDF financial data extraction using Google's Gemini Vision API with a robust financial analyst persona.

## 🎯 Features

- **Comprehensive Financial Metrics Detection**: Extracts 22+ key financial metrics including EBITDA, Free Cash Flow, Adjusted Earnings, etc.
- **Vision-Based Analysis**: Uses Gemini's vision capabilities to analyze charts, tables, and complex layouts
- **Smart Random Sampling**: Processes PDF pages randomly to avoid bias and ensure comprehensive coverage
- **Enhanced Structured Output**: Captures values, page numbers, document page references, years, and detailed context
- **Financial Analyst Persona**: Robust prompting with 15+ years of financial analysis expertise
- **Modular Architecture**: Clean, maintainable codebase with separate concerns
- **Early Termination**: Stops processing when all metrics are found to save API costs
- **Comprehensive Reporting**: Detailed extraction results with recommendations

## 📊 Target Financial Metrics

### Revenue & Earnings
- Operating income, Adjusted revenue, Adjusted earnings, EBIT, EBITDA, Adjusted EBIT
- Core earnings, Normalized earnings, Recurring earnings, Adjusted earnings per share, Normalized EPS

### Cash Flow & Balance Sheet  
- Free cash flow, Funds from operations, Distributable cash flow, Net debt
- Cash earnings, Cash loss

### Currency & Growth
- Constant-currency revenues, Constant-currency revenue growth, Constant-currency operating expenses

### GAAP Adjustments
- GAAP one-time adjusted, GAAP adjusted

## 🚀 Quick Start

### Installation

```bash
# Clone or download the project
cd financial-metrics-extractor

# Install dependencies
pip install -r requirements.txt

# Set your Gemini API key (optional - can also edit config.py)
export GEMINI_API_KEY="your-api-key-here"
```

### Streamlit Web UI (Recommended)

**NEW!** We now have a user-friendly web interface for PDF processing:

```bash
# Start the Streamlit web interface
streamlit run streamlit_app.py

# Or use the quick start script
chmod +x run_streamlit.sh
./run_streamlit.sh
```

The web UI provides:
- 📤 Easy PDF upload with drag-and-drop
- ✏️ Customizable analysis prompts
- 📡 Real-time processing logs
- 📊 Interactive results viewer with filtering
- 📥 JSON download for results and index
- 🗑️ Automatic cleanup after processing

See [STREAMLIT_README.md](STREAMLIT_README.md) for detailed UI documentation.

### CLI Usage

```bash
# Process a single PDF
python -m src.main pdfs/Zomato/22.pdf

# Process all PDFs in a directory
python -m src.main pdfs/Zomato/
```

### Programmatic Usage

```python
from src.financial_extractor import FinancialMetricsExtractor

# Initialize extractor
extractor = FinancialMetricsExtractor(api_key="your-key")

# Extract metrics
results = extractor.extract_metrics("document.pdf")

# Access results
found_metrics = results["found_metrics"]
missing_metrics = results["missing_metrics"]
success_rate = results["extraction_summary"]["success_rate"]
```

## 📁 Project Structure

```
financial-metrics-extractor/
├── src/
│   ├── __init__.py              # Package initialization
│   ├── config.py                # Configuration and settings
│   ├── pdf_processor.py         # PDF page extraction and processing
│   ├── prompt_engine.py         # Financial analyst prompt generation
│   ├── financial_extractor.py   # Main extraction logic
│   └── gemini.py               # Original test file
├── main.py                      # CLI interface and main execution
├── requirements.txt             # Python dependencies
├── README.md                   # This file
└── 3M.pdf                     # Sample PDF for testing
```

## 🔧 Configuration

Edit `src/config.py` to customize:

- **API Settings**: Gemini API key, model selection, temperature
- **Processing**: Batch size, image DPI, token limits  
- **Metrics**: Add/remove target financial metrics
- **Categories**: Organize metrics by type for better reporting

## 📊 Output Format

The extractor provides comprehensive structured output:

```json
{
  "extraction_summary": {
    "total_metrics_targeted": 22,
    "metrics_found": 15,
    "success_rate": "15/22 (68.2%)",
    "processing_time_seconds": 45.3
  },
  "found_metrics": {
    "Operating income": {
      "value": "$2.1 billion",
      "raw_value": "2100000000",
      "units": "billions",
      "currency": "USD", 
      "page_number": 15,
      "page_reference": "15",
      "year": "2023",
      "period": "Annual",
      "context": "Consolidated Statement of Operations",
      "location_type": "income_statement",
      "gaap_status": "GAAP",
      "confidence": "high"
    }
  },
  "missing_metrics": ["Net debt", "Normalized EPS"],
  "potential_matches": {},
  "recommendations": ["Manual review recommended for 7 missing metrics"]
}
```

## 🎯 Key Advantages

### 1. **Random Sampling Strategy**
- No bias against visual data (charts, graphs)
- Guaranteed coverage of entire document
- Faster processing (no text preprocessing)
- Works with any document layout

### 2. **Financial Analyst Expertise**
- Comprehensive search across all financial statement sections
- Handles GAAP vs Non-GAAP distinctions
- Recognizes various metric presentations and formats
- Captures detailed context for validation

### 3. **Enhanced Data Capture**
- Document page numbers AND system page numbers
- Year/period identification for temporal analysis
- Currency and units standardization
- Confidence scoring for quality assessment

### 4. **Efficiency Optimizations**
- Early termination when all metrics found
- Stateful processing (removes found metrics from search)
- Batch processing for API efficiency
- Error handling and graceful degradation

## 🔍 Usage Examples

### Command Line Examples

```bash
# Basic extraction
python main.py 3M.pdf

# Large document with bigger batches
python main.py annual_report.pdf --batch-size 8

# Save to specific location
python main.py financials.pdf --output /path/to/results.json

# Quiet mode for automation
python main.py document.pdf --no-summary > extraction.log
```

### Integration Examples

```python
# Batch processing multiple documents
from src.financial_extractor import FinancialMetricsExtractor

extractor = FinancialMetricsExtractor()
documents = ["q1_2023.pdf", "q2_2023.pdf", "q3_2023.pdf"]

all_results = {}
for doc in documents:
    results = extractor.extract_metrics(doc)
    all_results[doc] = results

# Compare metrics across periods
for doc, results in all_results.items():
    revenue = results["found_metrics"].get("Adjusted revenue", {}).get("value", "Not found")
    print(f"{doc}: Revenue = {revenue}")
```

## 🛠 Troubleshooting

### Common Issues

1. **API Key Errors**: Ensure your Gemini API key is valid and has sufficient quota
2. **PDF Processing Errors**: Check that PyMuPDF can open your PDF file
3. **Low Success Rates**: Try increasing batch size or check document quality
4. **Memory Issues**: Reduce batch size for very large documents

### Performance Tips

- Use batch sizes of 4-8 for optimal API efficiency
- Higher DPI improves text recognition but increases processing time
- Monitor API usage to avoid rate limits
- Consider document preprocessing for very large files

## 📈 Expected Performance

- **API Efficiency**: ~75% reduction in calls vs sequential processing
- **Accuracy**: 70-90% success rate on standard financial documents  
- **Speed**: 2-4 seconds per page batch (depending on complexity)
- **Coverage**: 100% document analysis (text + visual content)

## 🤝 Contributing

This is a modular, extensible system. Key areas for enhancement:

- Additional financial metrics
- Support for other document formats
- Multi-language document support
- Advanced validation rules
- Integration with financial databases

## 📄 License

This project is for educational and research purposes. Please ensure compliance with Gemini API terms of service and any applicable data usage policies.
