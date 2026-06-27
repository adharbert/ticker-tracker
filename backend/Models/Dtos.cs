namespace NewsMarketAgent.Api.Models;

public class SignalCallbackDto
{
    public Guid    ArticleId        { get; set; }
    public string  Ticker           { get; set; } = "";
    public bool    GovernancePassed { get; set; }
    public string? RejectionReason  { get; set; }
    public SignalPayloadDto? Signal  { get; set; }
}

public class SignalPayloadDto
{
    public string   EventType             { get; set; } = "";
    public string   Sentiment             { get; set; } = "";
    public decimal  Confidence            { get; set; }
    public string   ImpactSummary         { get; set; } = "";
    public string   TimeHorizon           { get; set; } = "";
    public string[] SourceCitations       { get; set; } = [];
    public string[] UncertaintyFactors    { get; set; } = [];
    public string   Disclaimer            { get; set; } = "";
    public int      SourceCredibilityTier { get; set; }
    public string[] GovernanceWarnings    { get; set; } = [];
    public bool     AlertSuppressed       { get; set; }
    public bool     RequiresHumanReview   { get; set; }
}

public class SignalResponseDto
{
    public string   Id                    { get; set; } = "";
    public string   Ticker                { get; set; } = "";
    public string   EventType             { get; set; } = "";
    public string   Sentiment             { get; set; } = "";
    public decimal  Confidence            { get; set; }
    public string   ImpactSummary         { get; set; } = "";
    public string   TimeHorizon           { get; set; } = "";
    public string[] SourceCitations       { get; set; } = [];
    public string[] UncertaintyFactors    { get; set; } = [];
    public string   Disclaimer            { get; set; } = "";
    public DateTime PublishedAt           { get; set; }
    public bool     GovernancePassed      { get; set; }
    public int      SourceCredibilityTier { get; set; }
    public string[] GovernanceWarnings    { get; set; } = [];
}
