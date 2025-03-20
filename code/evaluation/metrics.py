import pandas as pd
from sklearn.metrics import classification_report, accuracy_score
import argparse
import json
from pathlib import Path

def compute_metrics(y_true, y_pred):
    """
    Compute classification metrics and return them as a dictionary
    """
    # Overall accuracy
    accuracy = accuracy_score(y_true, y_pred)
    
    # Get detailed classification report
    report = classification_report(y_true, y_pred, output_dict=True)
    
    # Organize metrics
    metrics = {
        'overall': {
            'accuracy': accuracy
        },
        'per_class': {}
    }
    
    # Add per-class metrics
    for class_name, class_metrics in report.items():
        if class_name not in ['accuracy', 'macro avg', 'weighted avg']:
            metrics['per_class'][class_name] = {
                'precision': class_metrics['precision'],
                'recall': class_metrics['recall'],
                'f1-score': class_metrics['f1-score'],
                'support': class_metrics['support']
            }
    
    return metrics

def main():
    parser = argparse.ArgumentParser(description='Compute classification metrics')
    parser.add_argument('--input', type=str, required=True, help='Path to input CSV file')
    parser.add_argument('--output', type=str, required=True, help='Path to output metrics file')
    
    args = parser.parse_args()
    
    # Read the CSV file
    df = pd.read_csv(args.input)
    
    # Compute metrics
    metrics = compute_metrics(df['type'], df['assistant_label'])
    
    # Create DataFrame for metrics
    metrics_rows = []
    for class_name, class_metrics in metrics['per_class'].items():
        metrics_rows.append({
            'Class': class_name,
            'Precision': class_metrics['precision'],
            'Recall': class_metrics['recall'],
            'F1-score': class_metrics['f1-score'],
            'Support': class_metrics['support']
        })
    metrics_df = pd.DataFrame(metrics_rows)
    
    # Create nice string representation with tables
    output_str = "Classification Metrics Report\n"
    output_str += "===========================\n\n"
    
    output_str += f"Overall Accuracy: {metrics['overall']['accuracy']:.4f}\n\n"
    
    # Create table header
    output_str += "Per-class Metrics:\n"
    output_str += "-" * 80 + "\n"
    output_str += f"{'Class':<20} {'Precision':>12} {'Recall':>12} {'F1-score':>12} {'Support':>12}\n"
    output_str += "-" * 80 + "\n"
    
    # Add table rows
    for class_name, class_metrics in metrics['per_class'].items():
        output_str += f"{class_name:<20} "
        output_str += f"{class_metrics['precision']:>12.4f} "
        output_str += f"{class_metrics['recall']:>12.4f} "
        output_str += f"{class_metrics['f1-score']:>12.4f} "
        output_str += f"{int(class_metrics['support']):>12d}\n"
    
    output_str += "-" * 80 + "\n"

    # Print the formatted table to console
    print(output_str)

    # Save metrics in multiple formats
    output_path = Path(args.output)
    
    # Save JSON metrics
    with open(output_path.with_suffix('.json'), 'w') as f:
        json.dump(metrics, f, indent=4)
    
    # Save human-readable metrics
    with open(output_path.with_suffix('.txt'), 'w') as f:
        f.write(output_str)
    
    # Save CSV metrics
    metrics_df.to_csv(output_path.with_suffix('.csv'), index=False, float_format='%.4f')

if __name__ == "__main__":
    main()
