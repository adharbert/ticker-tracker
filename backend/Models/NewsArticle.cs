namespace NewsMarketAgent.Api.Models;

public class NewsArticle
{
    public Guid     Id          { get; set; } = Guid.NewGuid();
    public string   Ticker      { get; set; } = "";
    public string   Headline    { get; set; } = "";
    public string?  Body        { get; set; }
    public string?  SourceUrl   { get; set; }
    public string?  SourceName  { get; set; }
    public string?  DedupKey    { get; set; }
    public string?  EventType   { get; set; }
    public DateTime PublishedAt { get; set; }
    public DateTime IngestedAt  { get; set; } = DateTime.UtcNow;
    public bool     Processed   { get; set; }
}
