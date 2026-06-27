namespace NewsMarketAgent.Api.Models;

public class WatchlistItem
{
    public string   Ticker  { get; set; } = "";
    public string?  Name    { get; set; }
    public DateTime AddedAt { get; set; } = DateTime.UtcNow;
}

public record AddWatchlistItemDto(string Ticker, string? Name);
