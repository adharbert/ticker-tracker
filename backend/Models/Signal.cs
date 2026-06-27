namespace NewsMarketAgent.Api.Models;

public class Signal
{
    public Guid     Id                    { get; set; } = Guid.NewGuid();
    public string   Ticker                { get; set; } = "";
    public Guid?    ArticleId             { get; set; }
    public string   EventType             { get; set; } = "";
    public string   Sentiment             { get; set; } = "";
    public decimal  Confidence            { get; set; }
    public string   ImpactSummary         { get; set; } = "";
    public string   TimeHorizon           { get; set; } = "";
    public string[] SourceCitations       { get; set; } = [];
    public string[] UncertaintyFactors    { get; set; } = [];
    public string   Disclaimer            { get; set; } = "";
    public bool     GovernancePassed      { get; set; }
    public int      SourceCredibilityTier { get; set; }
    public bool     AlertSuppressed       { get; set; }
    public bool     RequiresHumanReview   { get; set; }
    public string[] GovernanceWarnings    { get; set; } = [];
    public DateTime PublishedAt           { get; set; }
    public DateTime CreatedAt             { get; set; } = DateTime.UtcNow;
}
