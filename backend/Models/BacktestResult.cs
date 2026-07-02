namespace NewsMarketAgent.Api.Models;

public class BacktestResult
{
    public int      Id               { get; set; }
    public string   Ticker           { get; set; } = "";
    public string?  EventType        { get; set; }
    public int      LookAheadDays    { get; set; }
    public int      SampleSize       { get; set; }
    public decimal? Accuracy         { get; set; }
    public string?  AccuracyNote     { get; set; }
    public decimal  BaselineAccuracy { get; set; }
    public decimal? VsBaseline       { get; set; }
    public string   Disclaimer       { get; set; } = "";
    public DateTime ComputedAt       { get; set; }
}
